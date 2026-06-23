#include "picdb_lidar_view.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <iomanip>
#include <map>
#include <memory>
#include <ostream>
#include <optional>
#include <queue>
#include <regex>
#include <set>
#include <stdexcept>
#include <tuple>
#include <unordered_set>
#include <utility>

#include "cell.h"
#include "net.h"
#include "pin.h"
#include "shape.h"

namespace picpr::lidar {
namespace {

constexpr double kEps = 1e-6;
constexpr double kGdsFactoryGcSizeX = 27.164;
constexpr double kGdsFactoryGcSizeY = 25.746;
constexpr double kGdsFactoryGcPinOffsetX = 0.0;
constexpr double kGdsFactoryGcPinOffsetY = 12.873;
constexpr double kGdsFactoryGcPinWidth = 0.5;
constexpr double kGdsFactoryGcPinOrient = 180.0;
constexpr double kGdsFactoryGcILoss = 2.0;

struct RectSize
{
  double width  = 0.0;
  double height = 0.0;
};

struct AdjustedPin
{
  double offsetX     = 0.0;
  double offsetY     = 0.0;
  double orientation = 0.0;
};

template <typename T>
using NamedPtrList = std::vector<std::pair<std::string, std::shared_ptr<T>>>;

double normalize360(double value)
{
  double normalized = std::fmod(value, 360.0);
  if (normalized < 0.0) {
    normalized += 360.0;
  }
  if (std::abs(normalized - 360.0) < kEps) {
    return 0.0;
  }
  return normalized;
}

double snapNearInteger(double value)
{
  const double rounded = std::round(value);
  return std::abs(value - rounded) < kEps ? rounded : value;
}

LidarPoint snapPoint(LidarPoint point)
{
  point.x = snapNearInteger(point.x);
  point.y = snapNearInteger(point.y);
  return point;
}

LidarBox snapBox(LidarBox box)
{
  box.lx = snapNearInteger(box.lx);
  box.ly = snapNearInteger(box.ly);
  box.ux = snapNearInteger(box.ux);
  box.uy = snapNearInteger(box.uy);
  return box;
}

RectSize rectSize(const std::shared_ptr<Shape>& shape)
{
  auto rect = std::dynamic_pointer_cast<Rect>(shape);
  if (!rect) {
    throw std::runtime_error(
        "LiDAR runtime DB currently supports Rect shapes only");
  }
  const auto box = rect->getShape();
  return {box.max_corner().x() - box.min_corner().x(),
          box.max_corner().y() - box.min_corner().y()};
}

template <typename TMap>
auto orderedEntries(const TMap& entries, bool deterministic)
{
  using ValueType = typename TMap::mapped_type::element_type;
  NamedPtrList<ValueType> ordered;
  ordered.reserve(entries.size());
  for (const auto& entry : entries) {
    ordered.push_back(entry);
  }
  if (deterministic) {
    std::sort(
        ordered.begin(), ordered.end(), [](const auto& lhs, const auto& rhs) {
          return lhs.first < rhs.first;
        });
  }
  return ordered;
}

bool swapsSize(const std::string& orientation)
{
  return orientation == "W" || orientation == "E" || orientation == "FW"
         || orientation == "FE";
}

int orientationBucket(double orientation)
{
  const double normalized = normalize360(orientation);
  if (std::abs(normalized - 0.0) < kEps) {
    return 0;
  }
  if (std::abs(normalized - 90.0) < kEps) {
    return 1;
  }
  if (std::abs(normalized - 180.0) < kEps) {
    return 2;
  }
  if (std::abs(normalized - 270.0) < kEps) {
    return 3;
  }
  return -1;
}

bool cpythonSetInsert(std::vector<std::optional<int>>& table, int key)
{
  constexpr std::size_t kLinearProbes = 9;
  constexpr std::size_t kPerturbShift = 5;

  const std::size_t mask    = table.size() - 1;
  std::size_t       hash    = static_cast<std::size_t>(key == -1 ? -2 : key);
  std::size_t       i       = hash & mask;
  std::size_t       perturb = hash;

  while (true) {
    std::size_t probes = (i + kLinearProbes <= mask) ? kLinearProbes : 0;
    std::size_t j      = i;
    while (true) {
      if (!table[j].has_value()) {
        table[j] = key;
        return true;
      }
      if (table[j].value() == key) {
        return false;
      }
      ++j;
      if (probes == 0) {
        break;
      }
      --probes;
    }
    perturb >>= kPerturbShift;
    i = (i * 5 + 1 + perturb) & mask;
  }
}

std::vector<std::optional<int>> cpythonSetResize(
    const std::vector<std::optional<int>>& oldTable,
    std::size_t                            used)
{
  std::size_t minUsed = used > 50000 ? used * 2 : used * 4;
  std::size_t newSize = 8;
  while (newSize <= minUsed) {
    newSize <<= 1;
  }

  std::vector<std::optional<int>> newTable(newSize);
  for (const auto& value : oldTable) {
    if (value.has_value()) {
      cpythonSetInsert(newTable, value.value());
    }
  }
  return newTable;
}

std::vector<int> cpythonIntSetIterationOrder(
    const std::vector<int>& insertionOrder)
{
  std::vector<std::optional<int>> table(8);
  std::size_t                     used = 0;
  std::size_t                     fill = 0;

  for (const int key : insertionOrder) {
    if (!cpythonSetInsert(table, key)) {
      continue;
    }
    ++used;
    ++fill;
    const std::size_t mask = table.size() - 1;
    if (fill * 5 >= mask * 3) {
      table = cpythonSetResize(table, used);
      fill  = used;
    }
  }

  std::vector<int> ordered;
  ordered.reserve(used);
  for (const auto& value : table) {
    if (value.has_value()) {
      ordered.push_back(value.value());
    }
  }
  return ordered;
}

AdjustedPin adjustPinForOrientation(const std::string& nodeOrient,
                                    double             nodeSizeX,
                                    double             nodeSizeY,
                                    double             pinOffsetX,
                                    double             pinOffsetY,
                                    double             pinOrient)
{
  const double ori = normalize360(pinOrient);
  if (nodeOrient == "N") {
    return {pinOffsetX, pinOffsetY, ori};
  }
  if (nodeOrient == "S") {
    return {nodeSizeX - pinOffsetX,
            nodeSizeY - pinOffsetY,
            normalize360(ori + 180.0)};
  }
  if (nodeOrient == "W") {
    return {nodeSizeY - pinOffsetY, pinOffsetX, normalize360(ori + 90.0)};
  }
  if (nodeOrient == "E") {
    return {pinOffsetY, nodeSizeX - pinOffsetX, normalize360(ori - 90.0)};
  }

  const std::array<double, 4> fnLookup    = {180.0, 90.0, 0.0, 270.0};
  const std::array<double, 4> fsLookup    = {0.0, 270.0, 180.0, 90.0};
  const std::array<double, 4> fwLookup    = {90.0, 0.0, 270.0, 180.0};
  const std::array<double, 4> feLookup    = {270.0, 180.0, 90.0, 0.0};
  const int                   orientIndex = static_cast<int>(ori / 90.0);
  if (orientIndex < 0 || orientIndex >= 4
      || std::abs(ori - static_cast<double>(orientIndex) * 90.0) > kEps) {
    throw std::runtime_error(
        "LiDAR mirror orientations require 0/90/180/270 pin orientations");
  }

  if (nodeOrient == "FN") {
    return {nodeSizeX - pinOffsetX, pinOffsetY, fnLookup[orientIndex]};
  }
  if (nodeOrient == "FS") {
    return {pinOffsetX, nodeSizeY - pinOffsetY, fsLookup[orientIndex]};
  }
  if (nodeOrient == "FW") {
    return {pinOffsetX, pinOffsetY, fwLookup[orientIndex]};
  }
  if (nodeOrient == "FE") {
    return {
        nodeSizeY - pinOffsetY, nodeSizeX - pinOffsetX, feLookup[orientIndex]};
  }

  throw std::runtime_error("Unsupported LiDAR orientation: " + nodeOrient);
}

std::string portNameForPin(const std::shared_ptr<Pin>& pin)
{
  const auto host = pin->getHostCell();
  if (!host) {
    throw std::runtime_error("LiDAR net pin has no host cell: "
                             + pin->getName());
  }
  return host->getName() + "," + pin->getName();
}

bool isLidarOpticalPin(const std::shared_ptr<Pin>& pin)
{
  if (!pin) {
    return false;
  }
  const auto pinName = pin->getName();
  if (!pinName.empty() && (pinName[0] == 'o' || pinName[0] == 'O')) {
    return true;
  }

  std::string xsection = pin->getCrossSection().getName();
  std::transform(xsection.begin(), xsection.end(), xsection.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  const bool looksElectrical = xsection.find("heater") != std::string::npos
                               || xsection.find("metal") != std::string::npos
                               || xsection.find("elect") != std::string::npos;
  return !looksElectrical && pin->getWidth() <= 1.0 + kEps;
}

bool isGdsFactoryGratingCoupler(const std::string& macroType)
{
  return macroType.find("grating_coupler") != std::string::npos;
}

void populateGdsFactoryGratingCouplerMacro(LidarMacro& macro)
{
  macro.sizeX = kGdsFactoryGcSizeX;
  macro.sizeY = kGdsFactoryGcSizeY;
  macro.iloss = kGdsFactoryGcILoss;

  LidarPinDefinition pinDef;
  pinDef.name        = "o1";
  pinDef.offsetX     = kGdsFactoryGcPinOffsetX;
  pinDef.offsetY     = kGdsFactoryGcPinOffsetY;
  pinDef.width       = kGdsFactoryGcPinWidth;
  pinDef.orientation = kGdsFactoryGcPinOrient;
  pinDef.layer       = 1;
  macro.pinIndex[pinDef.name] = macro.pins.size();
  macro.pins.push_back(std::move(pinDef));
}

void buildTopologyOrders(LidarRuntimeView& db)
{
  std::vector<int>                           nodeOrder;
  std::unordered_set<int>                    knownNodes;
  std::unordered_map<int, std::vector<int>>  successors;
  std::map<std::pair<int, int>, std::string> edgeLabels;
  std::map<std::pair<int, int>, double>      edgeWeights;
  std::unordered_map<int, int>               indegree;

  for (const auto& net : db.nets) {
    const int source = db.ports[net.sourcePortIndex].idBlk;
    const int target = db.ports[net.targetPortIndex].idBlk;
    if (!knownNodes.count(source)) {
      knownNodes.insert(source);
      nodeOrder.push_back(source);
    }
    if (!knownNodes.count(target)) {
      knownNodes.insert(target);
      nodeOrder.push_back(target);
    }

    const auto edgeKey = std::make_pair(source, target);
    const bool newEdge = edgeLabels.find(edgeKey) == edgeLabels.end();
    if (newEdge) {
      successors[source].push_back(target);
      indegree[target] += 1;
      if (indegree.find(source) == indegree.end()) {
        indegree[source] = 0;
      }
    }
    edgeLabels[edgeKey]  = net.netName;
    edgeWeights[edgeKey] = net.eulerDistance;
  }

  std::vector<int> currentLevel;
  for (const int node : nodeOrder) {
    if (indegree[node] == 0) {
      currentLevel.push_back(node);
    }
  }
  currentLevel = cpythonIntSetIterationOrder(currentLevel);

  std::unordered_set<std::string> visitedNets;
  while (!currentLevel.empty()) {
    std::vector<std::string> nets;
    std::vector<int>         nextLevel;
    std::unordered_set<int>  nextSeen;
    for (const int node : currentLevel) {
      for (const int neighbor : successors[node]) {
        if (!nextSeen.count(neighbor)) {
          nextSeen.insert(neighbor);
          nextLevel.push_back(neighbor);
        }
        const auto labelIt = edgeLabels.find(std::make_pair(node, neighbor));
        if (labelIt == edgeLabels.end()) {
          continue;
        }
        if (!visitedNets.count(labelIt->second)) {
          nets.push_back(labelIt->second);
          visitedNets.insert(labelIt->second);
        }
      }
    }
    if (!nets.empty()) {
      db.topologyOrders.push_back(std::move(nets));
    }
    currentLevel = cpythonIntSetIterationOrder(nextLevel);
  }
}

}  // namespace

std::string placementToString(Placement placement)
{
  switch (placement) {
    case Placement::FIXED:
      return "FIXED";
    case Placement::PLACED:
      return "PLACED";
    case Placement::UNPLACED:
    default:
      return "UNPLACED";
  }
}

std::string orientationFromCell(const Cell& cell)
{
  std::string  orient   = cell.getMirror() ? "F" : "";
  const double rotation = cell.getRotation();
  if (std::abs(rotation - 0.0) < kEps) {
    orient += "N";
  } else if (std::abs(rotation - 90.0) < kEps) {
    orient += "W";
  } else if (std::abs(rotation - 180.0) < kEps) {
    orient += "S";
  } else if (std::abs(rotation - 270.0) < kEps) {
    orient += "E";
  } else {
    throw std::runtime_error("Unsupported LiDAR cell rotation: "
                             + std::to_string(rotation));
  }
  return orient;
}

std::string componentNameForLidar(const std::string& picdbType)
{
  std::string component = picdbType;
  if (component.rfind("m_", 0) != 0) {
    return component;
  }
  if (component.find("mmi_I") != std::string::npos) {
    return "mmi";
  }
  if (component.find("mmi1x2") != std::string::npos) {
    return "mmi1x2";
  }
  if (component.find("mmi2x2") != std::string::npos) {
    return "mmi2x2";
  }
  if (component.find("mzi") != std::string::npos) {
    return "mzi";
  }
  if (component.find("straight_heater_metal") != std::string::npos) {
    if (component.find("_u_") != std::string::npos
        || component.find("undercut") != std::string::npos) {
      return "straight_heater_metal_undercut";
    }
    return "straight_heater_metal";
  }
  if (component.find("straight") != std::string::npos
      && component.find("heater") == std::string::npos) {
    return "straight";
  }
  if (component.find("grating_coupler") != std::string::npos) {
    return "grating_coupler_elliptical_lumerical";
  }
  return component;
}

LidarRuntimeView buildRuntimeViewFromDesign(const Design&         design,
                                        const LidarViewOptions& options)
{
  LidarRuntimeView db;
  db.designName = design.getName();
  const bool snapCoordinates = options.snapNearIntegerCoordinates;

  if (design.getShape()) {
    for (const auto& point : design.getShape()->getPoints()) {
      db.dieArea.push_back({point.x(), point.y()});
    }
  }

  int  blkIndex = 0;
  const auto cells
      = orderedEntries(design.getCells(), options.deterministicOrder);
  for (const auto& cellEntry : cells) {
    const auto&       cell      = cellEntry.second;
    const std::string macroType = cell->getType();
    const RectSize    cellSize  = rectSize(cell->getShape());
    const std::string orient    = orientationFromCell(*cell);

    if (!db.macroIndex.count(macroType)) {
      LidarMacro macro;
      macro.name = macroType;

      if (isGdsFactoryGratingCoupler(macroType)) {
        populateGdsFactoryGratingCouplerMacro(macro);
      } else {
        macro.sizeX = cellSize.width;
        macro.sizeY = cellSize.height;

        auto pinEntries
            = orderedEntries(cell->getPins(), options.deterministicOrder);
        for (const auto& pinEntry : pinEntries) {
          const auto&        pin = pinEntry.second;
          if (!isLidarOpticalPin(pin)) {
            continue;
          }
          LidarPinDefinition pinDef;
          pinDef.name        = pin->getName();
          pinDef.offsetX     = pin->getPosition().x() + cellSize.width / 2.0;
          pinDef.offsetY     = pin->getPosition().y() + cellSize.height / 2.0;
          pinDef.width       = pin->getWidth();
          pinDef.orientation = normalize360(pin->getRotation());
          pinDef.layer       = 1;
          macro.pinIndex[pinDef.name] = macro.pins.size();
          macro.pins.push_back(std::move(pinDef));
        }
      }

      db.macroIndex[macro.name] = db.macros.size();
      db.macros.push_back(std::move(macro));
    }

    const auto&  macro     = db.macros[db.macroIndex.at(macroType)];
    const double nodeSizeX = swapsSize(orient) ? macro.sizeY : macro.sizeX;
    const double nodeSizeY = swapsSize(orient) ? macro.sizeX : macro.sizeY;

    LidarInstance inst;
    inst.name            = cell->getName();
    inst.component       = componentNameForLidar(macroType);
    inst.macroType       = macroType;
    inst.placementStatus = placementToString(cell->getPlacement());
    inst.orientation     = orient;
    inst.lowerLeft       = {cell->getPosition().x() - nodeSizeX / 2.0,
                            cell->getPosition().y() - nodeSizeY / 2.0};
    if (snapCoordinates) {
      inst.lowerLeft = snapPoint(inst.lowerLeft);
    }
    inst.bbox            = {inst.lowerLeft.x,
                            inst.lowerLeft.y,
                            inst.lowerLeft.x + nodeSizeX,
                            inst.lowerLeft.y + nodeSizeY};
    if (snapCoordinates) {
      inst.bbox = snapBox(inst.bbox);
    }
    inst.idBlk           = blkIndex;
    inst.halo            = options.defaultHalo;

    const std::size_t instanceIdx = db.instances.size();
    db.instanceIndex[inst.name]   = instanceIdx;
    db.instances.push_back(std::move(inst));

    for (const auto& pinDef : macro.pins) {
      LidarPort port;
      port.instanceName = cell->getName();
      port.pinName      = pinDef.name;
      port.portName     = port.instanceName + "," + port.pinName;
      if (const auto dbPin = cell->getPin(pinDef.name)) {
        const auto pinPosition = dbPin->getAbsolutePosition();
        port.center = {pinPosition.x(), pinPosition.y()};
        port.width = dbPin->getWidth();
        port.orientation = normalize360(dbPin->getAbsoluteRotation());
      } else {
        const AdjustedPin adjusted = adjustPinForOrientation(orient,
                                                             macro.sizeX,
                                                             macro.sizeY,
                                                             pinDef.offsetX,
                                                             pinDef.offsetY,
                                                             pinDef.orientation);
        port.center = {db.instances[instanceIdx].lowerLeft.x + adjusted.offsetX,
                       db.instances[instanceIdx].lowerLeft.y + adjusted.offsetY};
        port.width = pinDef.width;
        port.orientation = adjusted.orientation;
      }
      if (snapCoordinates) {
        port.center = snapPoint(port.center);
      }
      port.idBlk       = db.instances[instanceIdx].idBlk;

      const int         bucket    = orientationBucket(port.orientation);
      const std::size_t portIdx   = db.ports.size();
      db.portIndex[port.portName] = portIdx;
      db.ports.push_back(std::move(port));
      if (bucket >= 0) {
        db.instances[instanceIdx].portsByOrientation[bucket].push_back(portIdx);
      }
    }

    ++blkIndex;
  }

  int  connectionCount = 0;
  const auto nets
      = orderedEntries(design.getNets(), options.deterministicOrder);
  for (const auto& netEntry : nets) {
    const auto& net  = netEntry.second;
    const auto  pins = net->getPins();
    if (pins.size() != 2) {
      throw std::runtime_error("LiDAR runtime DB expects two-pin nets, got "
                               + std::to_string(pins.size()) + " for "
                               + net->getName());
    }
    if (!isLidarOpticalPin(pins[0]) || !isLidarOpticalPin(pins[1])) {
      continue;
    }

    const std::string sourcePortName = portNameForPin(pins[0]);
    const std::string targetPortName = portNameForPin(pins[1]);
    if (!db.portIndex.count(sourcePortName)) {
      throw std::runtime_error("Missing source port in LiDAR runtime DB: "
                               + sourcePortName);
    }
    if (!db.portIndex.count(targetPortName)) {
      throw std::runtime_error("Missing target port in LiDAR runtime DB: "
                               + targetPortName);
    }

    const std::size_t sourceIdx = db.portIndex.at(sourcePortName);
    const std::size_t targetIdx = db.portIndex.at(targetPortName);
    const auto&       source    = db.ports[sourceIdx];
    const auto&       target    = db.ports[targetIdx];
    const double      dx        = source.center.x - target.center.x;
    const double      dy        = source.center.y - target.center.y;
    const double      euler     = std::sqrt(dx * dx + dy * dy);

    LidarNet lidarNet;
    lidarNet.netName
        = options.preserveOriginalNetNames
              ? net->getName()
              : options.generatedNetPrefix + std::to_string(connectionCount);
    lidarNet.designNetName     = net->getName();
    lidarNet.netID           = connectionCount;
    lidarNet.sourcePortName  = sourcePortName;
    lidarNet.targetPortName  = targetPortName;
    lidarNet.sourcePortIndex = sourceIdx;
    lidarNet.targetPortIndex = targetIdx;
    lidarNet.eulerDistance   = euler;
    lidarNet.compDist = static_cast<double>(static_cast<int>(euler / 1000.0));
    lidarNet.routingOrder = static_cast<int>(euler);

    db.ports[sourceIdx].netName   = lidarNet.netName;
    db.ports[targetIdx].netName   = lidarNet.netName;
    db.netIndex[lidarNet.netName] = db.nets.size();
    db.nets.push_back(std::move(lidarNet));
    ++connectionCount;
  }

  buildTopologyOrders(db);
  return db;
}

void writeRuntimeViewSummary(const LidarRuntimeView& db, std::ostream& os)
{
  os << std::fixed << std::setprecision(6);
  os << "DESIGN\t" << db.designName << "\n";
  os << "COUNTS\tinstances=" << db.instances.size()
     << "\tmacros=" << db.macros.size() << "\tports=" << db.ports.size()
     << "\tnets=" << db.nets.size()
     << "\ttopology_levels=" << db.topologyOrders.size() << "\n";

  for (const auto& macro : db.macros) {
    os << "MACRO\t" << macro.name << "\tsize=" << macro.sizeX << ","
       << macro.sizeY << "\tpins=" << macro.pins.size()
       << "\tiloss=" << macro.iloss << "\n";
    for (const auto& pin : macro.pins) {
      os << "PINDEF\t" << macro.name << "," << pin.name
         << "\toffset=" << pin.offsetX << "," << pin.offsetY
         << "\twidth=" << pin.width << "\torient=" << pin.orientation
         << "\tlayer=" << pin.layer << "\n";
    }
  }

  for (const auto& inst : db.instances) {
    os << "INST\t" << inst.name << "\tidBlk=" << inst.idBlk
       << "\tcomponent=" << inst.component << "\tmacro=" << inst.macroType
       << "\tstatus=" << inst.placementStatus << "\torient=" << inst.orientation
       << "\tll=" << inst.lowerLeft.x << "," << inst.lowerLeft.y
       << "\tbbox=" << inst.bbox.lx << "," << inst.bbox.ly << ","
       << inst.bbox.ux << "," << inst.bbox.uy
       << "\tports0=" << inst.portsByOrientation[0].size()
       << "\tports90=" << inst.portsByOrientation[1].size()
       << "\tports180=" << inst.portsByOrientation[2].size()
       << "\tports270=" << inst.portsByOrientation[3].size() << "\n";
  }

  for (const auto& port : db.ports) {
    os << "PORT\t" << port.portName << "\tidBlk=" << port.idBlk
       << "\tcenter=" << port.center.x << "," << port.center.y
       << "\twidth=" << port.width << "\torient=" << port.orientation
       << "\tnet=" << port.netName.value_or("None") << "\n";
  }

  for (const auto& net : db.nets) {
    os << "NET\t" << net.netName << "\tid=" << net.netID
       << "\tports=" << net.sourcePortName << "->" << net.targetPortName
       << "\teuler=" << net.eulerDistance << "\tcomp=" << net.compDist
       << "\torder=" << net.routingOrder << "\n";
  }

  for (std::size_t i = 0; i < db.topologyOrders.size(); ++i) {
    os << "TOPO\t" << i;
    for (const auto& netName : db.topologyOrders[i]) {
      os << "\t" << netName;
    }
    os << "\n";
  }
}

}  // namespace picpr::lidar
