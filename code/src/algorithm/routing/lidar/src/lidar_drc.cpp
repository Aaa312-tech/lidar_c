#include "lidar_drc.h"

#include <algorithm>
#include <cstdlib>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <ostream>
#include <sstream>
#include <stdexcept>

namespace picpr::lidar
{
namespace
{

int truncToInt(double value)
{
  return static_cast<int>(value);
}

std::string groupName(const std::string& instanceName, int orientation)
{
  return instanceName + "_" + std::to_string(orientation);
}

std::vector<std::string>& ensureGroup(LidarRuntimeView& db, const std::string& name)
{
  auto it = db.groupNets.find(name);
  if (it == db.groupNets.end()) {
    db.groupOrder.push_back(name);
    it = db.groupNets.emplace(name, std::vector<std::string>{}).first;
  }
  return it->second;
}

bool parseTracePos(const char* value, std::array<int, 3>& pos)
{
  if (value == nullptr) {
    return false;
  }
  std::stringstream ss(value);
  char comma1 = 0;
  char comma2 = 0;
  return static_cast<bool>(ss >> pos[0] >> comma1 >> pos[1] >> comma2 >> pos[2])
         && comma1 == ',' && comma2 == ',';
}

}  // namespace

LidarDrcManager::LidarDrcManager(LidarRuntimeView& db,
                                 const LidarDrcConfig& config)
    : _db(db),
      _config(config),
      _bitmap(db.dieArea, config.gridResolution),
      _radius(static_cast<int>(std::ceil(config.bendRadius / config.gridResolution))),
      _portLength(static_cast<int>(
          std::ceil((config.maxCrossing + config.bendRadius) / config.gridResolution)))
{
}

void LidarDrcManager::initDRC()
{
  initBitmap();
}

void LidarDrcManager::initBitmap()
{
  _bitmap.initMap(_db.instances);
}

void LidarDrcManager::initPorts()
{
  for (const auto& instance : _db.instances) {
    spreadPorts(instance.name, instance.portsByOrientation[0], 0);
    spreadPorts(instance.name, instance.portsByOrientation[1], 90);
    spreadPorts(instance.name, instance.portsByOrientation[2], 180);
    spreadPorts(instance.name, instance.portsByOrientation[3], 270);
  }
}

void LidarDrcManager::setRoutingBendParameters(int bend90,
                                               int bend45Part1,
                                               int bend45Part2,
                                               int predictLength)
{
  _radius = bend90;
  _bend45Part1 = bend45Part1;
  _bend45Part2 = bend45Part2;
  _predictLength = predictLength;
}

std::array<int, 2> LidarDrcManager::orientationStep(double orientation) const
{
  const int bucket = orientationBucket(orientation);
  switch (bucket) {
    case 0:
      return {1, 0};
    case 1:
      return {0, 1};
    case 2:
      return {-1, 0};
    case 3:
      return {0, -1};
    default:
      throw std::runtime_error("Unsupported LiDAR DRC orientation");
  }
}

std::array<int, 2> LidarDrcManager::checkStep(int orientation) const
{
  switch ((orientation % 360 + 360) % 360) {
    case 0:
      return {1, 0};
    case 45:
      return {1, 1};
    case 90:
      return {0, 1};
    case 135:
      return {-1, 1};
    case 180:
      return {-1, 0};
    case 225:
      return {-1, -1};
    case 270:
      return {0, -1};
    case 315:
      return {1, -1};
    default:
      throw std::runtime_error("Unsupported LiDAR DRC check orientation");
  }
}

int LidarDrcManager::orientationBucket(double orientation) const
{
  const int rounded = static_cast<int>(std::round(orientation));
  switch ((rounded % 360 + 360) % 360) {
    case 0:
      return 0;
    case 90:
      return 1;
    case 180:
      return 2;
    case 270:
      return 3;
    default:
      return -1;
  }
}

int LidarDrcManager::portCountForOrientation(const LidarInstance& instance,
                                             double orientation) const
{
  const int bucket = orientationBucket(orientation);
  if (bucket < 0) {
    return 0;
  }
  return static_cast<int>(instance.portsByOrientation[static_cast<std::size_t>(bucket)].size());
}

std::vector<int> LidarDrcManager::linspaceInt(int start, int stop, int count) const
{
  std::vector<int> values;
  if (count <= 0) {
    return values;
  }
  values.reserve(static_cast<std::size_t>(count));
  if (count == 1) {
    values.push_back(start);
    return values;
  }
  const double step = static_cast<double>(stop - start) / static_cast<double>(count - 1);
  for (int i = 0; i < count; ++i) {
    values.push_back(truncToInt(static_cast<double>(start) + step * i));
  }
  return values;
}

bool LidarDrcManager::isBlockage(const std::array<int, 2>& loc) const
{
  return _bitmap.inBounds(loc[0], loc[1])
         && _bitmap.at(loc[0], loc[1]).typeString() == "blk";
}

void LidarDrcManager::markPortGrid(LidarPort& port, const std::array<int, 2>& loc)
{
  if (!port.netName.has_value()) {
    return;
  }
  if (_bitmap.inBounds(loc[0], loc[1])) {
    _bitmap.at(loc[0], loc[1]).updatePort(port.netName.value());
  }
  port.portGrids.push_back(loc);
}

LidarDrcCheck LidarDrcManager::checkSingleNode(const std::array<int, 3>& index,
                                               const std::string& checkNet) const
{
  return checkSingleNode(index[0], index[1], checkNet);
}

LidarDrcCheck LidarDrcManager::checkSingleNode(int x,
                                               int y,
                                               const std::string& /*checkNet*/) const
{
  if (!_bitmap.inBounds(x, y)) {
    return {true, "blk", std::nullopt, std::string("__out_of_bounds__")};
  }

  const auto& node = _bitmap.at(x, y);
  switch (node.kind) {
    case BitmapNodeKind::Empty:
      return {false, "empty", std::nullopt, std::nullopt};
    case BitmapNodeKind::Blockage:
      return {true, "blk", std::nullopt, node.blkID};
    case BitmapNodeKind::Port:
      return {true, "port", std::nullopt, node.blkID};
    case BitmapNodeKind::Compound:
      return {true,
              "compound",
              std::nullopt,
              node.netIDs.empty() ? std::optional<std::string>{}
                                  : std::optional<std::string>{node.netIDs.front()}};
    case BitmapNodeKind::Waveguide:
      return {true,
              node.waveguideType.has_value() ? std::to_string(node.waveguideType.value())
                                             : "waveguide",
              node.waveguideType,
              node.netIDs.empty() ? std::optional<std::string>{}
                                  : std::optional<std::string>{node.netIDs.front()}};
  }
  return {false, "empty", std::nullopt, std::nullopt};
}

int LidarDrcManager::checkSpacing(const std::array<int, 3>& node,
                                  int checkRegion,
                                  const std::set<std::string>& groups) const
{
  auto clip2 = [&](int x, int y) {
    return std::array<int, 2>{
        std::min(std::max(x, 0), _bitmap.width() - 1),
        std::min(std::max(y, 0), _bitmap.height() - 1)};
  };
  auto occupiedCost = [&](const BitmapNode& bitmapNode) {
    const auto type = bitmapNode.typeString();
    if (type == "empty") {
      return 0;
    }
    if (type == "blk" || type == "port") {
      return 1;
    }
    if (!bitmapNode.netIDs.empty()
        && groups.find(bitmapNode.netIDs.front()) != groups.end()) {
      return 0;
    }
    return 1;
  };

  const int x = node[0];
  const int y = node[1];
  const int ori = (node[2] % 360 + 360) % 360;
  int count = 0;
  auto addAt = [&](int cx, int cy) {
    const auto clipped = clip2(cx, cy);
    count += occupiedCost(_bitmap.at(clipped[0], clipped[1]));
  };

  for (int i = 1; i <= checkRegion; ++i) {
    switch (ori) {
      case 0:
      case 180:
        addAt(x, y + i);
        addAt(x, y - i);
        break;
      case 90:
      case 270:
        addAt(x + i, y);
        addAt(x - i, y);
        break;
      case 45:
      case 225:
        addAt(x + i, y - i);
        addAt(x - i, y + i);
        break;
      case 135:
      case 315:
        addAt(x + i, y + i);
        addAt(x - i, y - i);
        break;
      default:
        break;
    }
  }
  return count;
}

bool LidarDrcManager::crossingCheck(const LidarNet& host,
                                    const LidarNet& slave,
                                    int straightCount,
                                    bool manhattan,
                                    double& halfSize) const
{
  const double straightLength = straightCount * _config.gridResolution
                                * (manhattan ? 1.0 : std::sqrt(2.0));
  if (host.width == slave.width && host.wavelength == slave.wavelength
      && host.material == slave.material && straightLength > host.halfSize) {
    halfSize = host.halfSize;
    return true;
  }
  halfSize = 0.0;
  return false;
}

LidarDrcResult LidarDrcManager::bViolateDRC(const LidarDrcNode& currentNode,
                                            const LidarDrcStep& step,
                                            bool crossingEnable,
                                            const std::string& netName,
                                            bool enablePrediction) const
{
  const auto currentNodePos = currentNode.pos;
  const int crossingBudget = currentNode.crossingBudget;
  const int straightCount = currentNode.straightCount;
  const int checkOri = step.orientation;
  const auto checkstep = checkStep(checkOri);
  int checkX = currentNodePos[0];
  int checkY = currentNodePos[1];
  const auto nbType = step.type;
  std::array<int, 3> tracePos = {0, 0, 0};
  const char* traceNet = std::getenv("PICDB_LIDAR_TRACE_NET");
  const bool traceDrc = traceNet != nullptr && netName == traceNet
                        && parseTracePos(std::getenv("PICDB_LIDAR_TRACE_POS"), tracePos)
                        && currentNodePos == tracePos;

  auto resultFor = [](bool violated,
                      std::optional<std::array<int, 3>> crossingNeighbor = std::nullopt,
                      std::string resultType = {},
                      std::set<std::string> violatedNets = {},
                      std::optional<std::string> crossingNet = std::nullopt) {
    LidarDrcResult result;
    result.violated = violated;
    result.crossingNeighbor = std::move(crossingNeighbor);
    result.resultType = std::move(resultType);
    result.violatedNets = std::move(violatedNets);
    result.crossingNet = std::move(crossingNet);
    return result;
  };
  auto violatedSet = [](const LidarDrcCheck& check) {
    std::set<std::string> nets;
    if (check.netName.has_value()) {
      nets.insert(check.netName.value());
    }
    return nets;
  };
  auto isOwnPort = [&](const LidarDrcCheck& check) {
    return check.type == "port" && check.netName.has_value()
           && check.netName.value() == netName;
  };
  auto isHardType = [](const LidarDrcCheck& check) {
    return check.type == "blk" || check.type == "compound" || check.type == "port";
  };
  auto waveguideNetReady = [&](const LidarDrcCheck& check) {
    if (!check.netName.has_value()) {
      return false;
    }
    auto it = _db.netIndex.find(check.netName.value());
    return it != _db.netIndex.end() && _db.nets[it->second].currentBudget > 0;
  };
  auto writeTraceCheck = [&](const char* phase,
                             int x,
                             int y,
                             int ori,
                             const LidarDrcCheck& check) {
    if (!traceDrc) {
      return;
    }
    std::cerr << "TRACE_DRC_CHECK"
              << "\tnet=" << netName
              << "\tcurrent=" << currentNodePos[0] << "," << currentNodePos[1]
              << "," << currentNodePos[2]
              << "\tstep=" << step.dx << "," << step.dy << ","
              << step.orientation << "," << step.type
              << "\tphase=" << phase
              << "\tcheck=" << x << "," << y << "," << ori
              << "\tviolated=" << (check.violated ? 1 : 0)
              << "\ttype=" << check.type;
    if (check.netName.has_value()) {
      std::cerr << "\tnet_name=" << check.netName.value();
    }
    if (check.waveguideType.has_value()) {
      std::cerr << "\twgtype=" << check.waveguideType.value();
    }
    std::cerr << "\n";
  };
  auto writeTraceCrossing = [&](const char* reason,
                                const LidarDrcCheck& check,
                                double halfSize,
                                int checkingSize) {
    if (!traceDrc) {
      return;
    }
    std::cerr << "TRACE_DRC_CROSSING"
              << "\tnet=" << netName
              << "\tcurrent=" << currentNodePos[0] << "," << currentNodePos[1]
              << "," << currentNodePos[2]
              << "\tstep=" << step.dx << "," << step.dy << ","
              << step.orientation << "," << step.type
              << "\treason=" << reason
              << "\tstraight_count=" << straightCount
              << "\tcrossing_budget=" << crossingBudget
              << "\thalf_size=" << halfSize
              << "\tchecking_size=" << checkingSize
              << "\ttype=" << check.type;
    if (check.netName.has_value()) {
      std::cerr << "\tnet_name=" << check.netName.value();
      auto netIt = _db.netIndex.find(check.netName.value());
      if (netIt != _db.netIndex.end()) {
        std::cerr << "\tother_current_budget="
                  << _db.nets[netIt->second].currentBudget;
      }
    }
    if (check.waveguideType.has_value()) {
      std::cerr << "\twgtype=" << check.waveguideType.value();
    }
    std::cerr << "\n";
  };

  if (nbType == "straight_0" || nbType == "straight_45") {
    checkX += checkstep[0];
    checkY += checkstep[1];
    const auto check = checkSingleNode(checkX, checkY, netName);
    writeTraceCheck("primary", checkX, checkY, checkOri, check);
    if (!check.violated) {
      return resultFor(false);
    }
    if (isOwnPort(check)) {
      return resultFor(false);
    }
    if (isHardType(check) || !check.waveguideType.has_value()) {
      return resultFor(true, std::nullopt, check.type, violatedSet(check));
    }

    const int nType = check.waveguideType.value();
    const bool crossingOrientation = nbType == "straight_0"
                                         ? std::abs(checkOri - nType) == 90
                                         : ((checkOri + nType) % 180) == 0;
    if (!crossingOrientation || !crossingEnable || crossingBudget <= 0
        || !waveguideNetReady(check)) {
      writeTraceCrossing("disabled_or_orientation", check, 0.0, 0);
      return resultFor(true, std::nullopt, check.type, violatedSet(check));
    }

    const auto& host = _db.nets[_db.netIndex.at(netName)];
    const auto& slave = _db.nets[_db.netIndex.at(check.netName.value())];
    double halfSize = 0.0;
    if (!crossingCheck(host, slave, straightCount + 1, nbType == "straight_0", halfSize)) {
      writeTraceCrossing("crossing_check_failed", check, halfSize, 0);
      return resultFor(true, std::nullopt, check.type, violatedSet(check));
    }

    const int checkingSize = static_cast<int>(
        std::round(halfSize / _config.gridResolution + 0.1));
    if (nbType == "straight_0") {
      if (checkOri == 0 || checkOri == 180) {
        for (int i = 1; i <= checkingSize; ++i) {
          const auto upper = checkSingleNode(checkX, checkY + i, netName);
          const auto lower = checkSingleNode(checkX, checkY - i, netName);
          writeTraceCheck("orthogonal_span", checkX, checkY + i, checkOri, upper);
          writeTraceCheck("orthogonal_span", checkX, checkY - i, checkOri, lower);
          if (upper.waveguideType != nType || lower.waveguideType != nType) {
            writeTraceCrossing("orthogonal_span_failed", check, halfSize, checkingSize);
            return resultFor(true, std::nullopt, check.type, violatedSet(check));
          }
        }
      } else {
        for (int i = 1; i <= checkingSize; ++i) {
          const auto right = checkSingleNode(checkX + i, checkY, netName);
          const auto left = checkSingleNode(checkX - i, checkY, netName);
          writeTraceCheck("orthogonal_span", checkX + i, checkY, checkOri, right);
          writeTraceCheck("orthogonal_span", checkX - i, checkY, checkOri, left);
          if (right.waveguideType != nType || left.waveguideType != nType) {
            writeTraceCrossing("orthogonal_span_failed", check, halfSize, checkingSize);
            return resultFor(true, std::nullopt, check.type, violatedSet(check));
          }
        }
      }
    } else {
      if (checkOri == 45 || checkOri == 225) {
        for (int i = 1; i <= checkingSize; ++i) {
          const auto left = checkSingleNode(checkX - i, checkY + i, netName);
          const auto right = checkSingleNode(checkX + i, checkY - i, netName);
          writeTraceCheck("diagonal_span", checkX - i, checkY + i, checkOri, left);
          writeTraceCheck("diagonal_span", checkX + i, checkY - i, checkOri, right);
          if (left.waveguideType != nType || right.waveguideType != nType) {
            writeTraceCrossing("diagonal_span_failed", check, halfSize, checkingSize);
            return resultFor(true, std::nullopt, check.type, violatedSet(check));
          }
        }
      } else if (checkOri == 135 || checkOri == 315) {
        for (int i = 1; i <= checkingSize; ++i) {
          const auto left = checkSingleNode(checkX + i, checkY + i, netName);
          const auto right = checkSingleNode(checkX - i, checkY - i, netName);
          writeTraceCheck("diagonal_span", checkX + i, checkY + i, checkOri, left);
          writeTraceCheck("diagonal_span", checkX - i, checkY - i, checkOri, right);
          if (left.waveguideType != nType || right.waveguideType != nType) {
            writeTraceCrossing("diagonal_span_failed", check, halfSize, checkingSize);
            return resultFor(true, std::nullopt, check.type, violatedSet(check));
          }
        }
      }
    }

    std::array<int, 3> crossingNeighbor = {checkX, checkY, checkOri};
    for (int i = 0; i < std::max(0, checkingSize); ++i) {
      checkX += nbType == "straight_45" ? step.dx : checkstep[0];
      checkY += nbType == "straight_45" ? step.dy : checkstep[1];
      crossingNeighbor = {checkX, checkY, checkOri};
      const auto cr = checkSingleNode(crossingNeighbor, netName);
      writeTraceCheck("crossing_neighbor", checkX, checkY, checkOri, cr);
      if (cr.violated && !isOwnPort(cr)) {
        writeTraceCrossing("crossing_neighbor_blocked", check, halfSize, checkingSize);
        return resultFor(true, std::nullopt, check.type, violatedSet(check));
      }
    }
    return resultFor(true,
                     crossingNeighbor,
                     nbType == "straight_0" ? "crossing_0" : "crossing_45",
                     {},
                     check.netName);
  }

  auto checkAndAccumulate = [&](int x,
                                int y,
                                int ori,
                                std::set<std::string>& violatedNets,
                                LidarDrcResult& earlyResult) {
    const auto check = checkSingleNode(std::array<int, 3>{x, y, ori}, netName);
    writeTraceCheck("body", x, y, ori, check);
    if (!check.violated || isOwnPort(check)) {
      return false;
    }
    if (check.type == "port" || check.type == "blk") {
      earlyResult = resultFor(true, std::nullopt, check.type, violatedSet(check));
      return true;
    }
    if (check.netName.has_value()) {
      violatedNets.insert(check.netName.value());
    }
    return false;
  };
  auto predictionBlocked = [&](int x, int y, int ori, const std::array<int, 2>& dir) {
    for (int i = 0; i < _predictLength; ++i) {
      x += dir[0];
      y += dir[1];
      const auto check = checkSingleNode(std::array<int, 3>{x, y, ori}, netName);
      writeTraceCheck("prediction", x, y, ori, check);
      if (check.violated && !isOwnPort(check)) {
        return true;
      }
    }
    return false;
  };

  if (nbType == "bend_45_2" || nbType == "bend_45_1") {
    std::set<std::string> violatedNets;
    LidarDrcResult earlyResult;
    const int ori1 = currentNodePos[2];
    const int ori2 = checkOri;
    const auto checkstep1 = checkStep(ori1);
    const auto checkstep2 = checkstep;
    const int firstLen = nbType == "bend_45_2" ? _bend45Part2 : _bend45Part1;
    const int secondLen = nbType == "bend_45_2" ? _bend45Part1 : _bend45Part2;
    for (int i = 0; i < firstLen; ++i) {
      checkX += checkstep1[0];
      checkY += checkstep1[1];
      if (checkAndAccumulate(checkX, checkY, ori1, violatedNets, earlyResult)) {
        return earlyResult;
      }
    }
    for (int i = 0; i < secondLen; ++i) {
      checkX += checkstep2[0];
      checkY += checkstep2[1];
      if (checkAndAccumulate(checkX, checkY, ori2, violatedNets, earlyResult)) {
        return earlyResult;
      }
    }
    if (violatedNets.empty() && enablePrediction && crossingEnable
        && predictionBlocked(checkX, checkY, checkOri, checkstep2)) {
      return resultFor(true);
    }
    if (!violatedNets.empty()) {
      return resultFor(true, std::nullopt, {}, violatedNets);
    }
    return resultFor(false);
  }

  if (nbType == "bend_90") {
    std::set<std::string> violatedNets;
    LidarDrcResult earlyResult;
    const int ori1 = currentNodePos[2];
    const int ori2 = checkOri;
    const int ori3 = (ori1 + ori2) / 2;
    const auto checkstep1 = checkStep(ori1);
    const auto checkstep2 = checkstep;
    for (int i = 0; i < _bend45Part1; ++i) {
      checkX += checkstep1[0];
      checkY += checkstep1[1];
      if (checkAndAccumulate(checkX, checkY, ori1, violatedNets, earlyResult)) {
        return earlyResult;
      }
    }
    for (int i = 0; i < _radius - _bend45Part1; ++i) {
      checkX += checkstep1[0] + checkstep2[0];
      checkY += checkstep1[1] + checkstep2[1];
      if (checkAndAccumulate(checkX, checkY, ori3, violatedNets, earlyResult)) {
        return earlyResult;
      }
    }
    for (int i = 0; i < _bend45Part1; ++i) {
      checkX += checkstep2[0];
      checkY += checkstep2[1];
      if (checkAndAccumulate(checkX, checkY, ori2, violatedNets, earlyResult)) {
        return earlyResult;
      }
    }
    if (violatedNets.empty() && enablePrediction && crossingEnable
        && predictionBlocked(checkX, checkY, ori2, checkstep2)) {
      return resultFor(true);
    }
    if (!violatedNets.empty()) {
      return resultFor(true, std::nullopt, {}, violatedNets);
    }
    return resultFor(false);
  }

  return resultFor(false);
}

void LidarDrcManager::updatePathBitmap(const std::vector<std::array<int, 3>>& path,
                                       const std::string& netName)
{
  auto wgTypeFor = [](int orientation) {
    switch ((orientation % 360 + 360) % 360) {
      case 90:
      case 270:
        return 90;
      case 45:
      case 225:
        return 45;
      case 135:
      case 315:
        return 135;
      default:
        return 180;
    }
  };
  auto angleDelta = [](int first, int second) {
    int angle = std::abs(((second - first) % 360 + 360) % 360);
    if (angle > 180) {
      angle = 360 - angle;
    }
    return angle;
  };

  auto netIt = _db.netIndex.find(netName);
  if (netIt == _db.netIndex.end()) {
    return;
  }
  auto& net = _db.nets[netIt->second];
  const bool interpolateCrossingGaps = !net.crossingNets.empty();
  struct MarkedCell
  {
    int wgType = 0;
    int priority = 0;
  };
  std::map<std::array<int, 2>, MarkedCell> marked;
  auto replaceMarkedType = [&](int x, int y, int wgType) {
    auto& node = _bitmap.at(x, y);
    auto typeIt = node.wgTypes.find(netName);
    if (typeIt == node.wgTypes.end()) {
      return;
    }
    typeIt->second = wgType;
    if (node.kind == BitmapNodeKind::Waveguide) {
      node.waveguideType = wgType;
    }
  };
  auto mark = [&](int x, int y, int wgType, int priority) {
    if (!_bitmap.inBounds(x, y)) {
      return;
    }
    const std::array<int, 2> loc = {x, y};
    auto [it, inserted] = marked.emplace(loc, MarkedCell{wgType, priority});
    if (!inserted) {
      if (it->second.priority > priority) {
        return;
      }
      if (it->second.priority == priority && it->second.wgType == wgType) {
        return;
      }
      // Match Python updateBitmap ordering: curve rectangles are written
      // before straight rectangles, while our synthetic interpolation is only
      // a helper for crossing gaps.  Therefore real path straight footprints
      // can override curves, and curves can override interpolated straights.
      it->second = MarkedCell{wgType, priority};
      replaceMarkedType(x, y, wgType);
      return;
    }
    net.rwguide.insert(loc);
    _bitmap.at(x, y).updateWaveguide(netName, wgType);
  };
  auto markDiagonalFootprint = [&](int x,
                                   int y,
                                   int orientation,
                                   int priority,
                                   int suppressedFringe) {
    // Python LiDAR rasterizes diagonal waveguides from the extruded polygon
    // footprint. Interior diagonal cells occupy both y-neighbors at the 2um
    // benchmark resolution, but endpoint caps near a turn are asymmetric after
    // gdsfactory smooth/extrude rasterization.
    if (suppressedFringe != -1) {
      mark(x, y - 1, wgTypeFor(orientation), priority);
    }
    mark(x, y, wgTypeFor(orientation), priority);
    if (suppressedFringe != 1) {
      mark(x, y + 1, wgTypeFor(orientation), priority);
    }
  };
  auto markPointFootprint = [&](int x,
                                 int y,
                                 int orientation,
                                 int priority,
                                 int nextOrientation = -1) {
    const int normalized = (orientation % 360 + 360) % 360;
    if (normalized == 45 || normalized == 135 || normalized == 225
        || normalized == 315) {
      int suppressedFringe = 0;
      if (nextOrientation >= 0) {
        const int normalizedNext = (nextOrientation % 360 + 360) % 360;
        if ((normalized == 45 && normalizedNext == 0)
            || (normalized == 135 && normalizedNext == 180)) {
          suppressedFringe = 1;
        } else {
          suppressedFringe = -1;
        }
      }
      markDiagonalFootprint(x, y, normalized, priority, suppressedFringe);
    } else {
      mark(x, y, wgTypeFor(normalized), priority);
    }
  };
  auto markInterpolatedStraightSegment = [&](const std::array<int, 3>& from,
                                             const std::array<int, 3>& to) {
    if (!interpolateCrossingGaps) {
      return;
    }
    if (from[2] != to[2]) {
      return;
    }
    const int dx = to[0] - from[0];
    const int dy = to[1] - from[1];
    const int steps = std::max(std::abs(dx), std::abs(dy));
    if (steps <= 1) {
      return;
    }
    for (int step = 1; step < steps; ++step) {
      const double ratio = static_cast<double>(step) / static_cast<double>(steps);
      const int x = static_cast<int>(static_cast<double>(from[0])
                                     + static_cast<double>(dx) * ratio);
      const int y = static_cast<int>(static_cast<double>(from[1])
                                     + static_cast<double>(dy) * ratio);
      markPointFootprint(x, y, from[2], 0);
    }
  };
  auto markBendFootprint = [&](const std::array<int, 3>& current, int nextOrientation) {
    const int x = current[0];
    const int y = current[1];
    const int ori1 = current[2];
    const int ori2 = nextOrientation;
    const auto step1 = checkStep(ori1);
    const auto step2 = checkStep(ori2);
    const int angle = angleDelta(ori1, ori2);
    // gdsfactory's rasterized route classifies the turn cap as curve/bend.
    // Keep that bend type when it overlaps the synthetic straight footprint
    // inserted by _process_bend at the same grid point.
    constexpr int bendPriority = 3;
    mark(x, y, 1, bendPriority);
    if (angle == 90) {
      // Quarter bend footprint: cells spanned by the pre-turn tangent and the
      // post-turn tangent, matching the integer cells produced by LiDAR's
      // gdsfactory polygon-boundary rasterizer for width=0.5.
      const int extent = std::max(0, _radius - 1);
      for (int a = 0; a <= extent; ++a) {
        for (int b = 0; b + a <= extent; ++b) {
          mark(x - a * step1[0] + b * step2[0],
               y - a * step1[1] + b * step2[1],
               1,
               bendPriority);
        }
      }
      return;
    }
    if (angle == 45) {
      // Upstream LiDAR rasterizes the gdsfactory Euler-bend polygon boundary
      // into a four-cell T footprint at the processed 45-degree bend point.
      // A simple step1/step2 corner formula places one cell diagonally outside
      // that footprint, which changes later DRC decisions on tied A* paths.
      std::array<std::array<int, 2>, 4> offsets = {
          std::array<int, 2>{0, 0},
          std::array<int, 2>{-1, 0},
          std::array<int, 2>{1, 0},
          std::array<int, 2>{0, 1}};
      const int normalized1 = (ori1 % 360 + 360) % 360;
      const int normalized2 = (ori2 % 360 + 360) % 360;
      const auto horizontalUp = std::array<std::array<int, 2>, 4>{
          std::array<int, 2>{0, 0},
          std::array<int, 2>{-1, 0},
          std::array<int, 2>{1, 0},
          std::array<int, 2>{0, 1}};
      const auto horizontalDown = std::array<std::array<int, 2>, 4>{
          std::array<int, 2>{0, 0},
          std::array<int, 2>{-1, 0},
          std::array<int, 2>{1, 0},
          std::array<int, 2>{0, -1}};
      const auto verticalLeft = std::array<std::array<int, 2>, 4>{
          std::array<int, 2>{0, 0},
          std::array<int, 2>{0, -1},
          std::array<int, 2>{0, 1},
          std::array<int, 2>{-1, 0}};
      const auto verticalRight = std::array<std::array<int, 2>, 4>{
          std::array<int, 2>{0, 0},
          std::array<int, 2>{0, -1},
          std::array<int, 2>{0, 1},
          std::array<int, 2>{1, 0}};

      switch (normalized1 * 1000 + normalized2) {
        case 45:      // 0 -> 45
        case 180135:  // 180 -> 135
        case 225180:  // 225 -> 180
        case 315000:  // 315 -> 0
          offsets = horizontalUp;
          break;
        case 315:     // 0 -> 315
        case 45000:   // 45 -> 0
        case 135180:  // 135 -> 180
        case 180225:  // 180 -> 225
          offsets = horizontalDown;
          break;
        case 45090:   // 45 -> 90
        case 90135:   // 90 -> 135
        case 270225:  // 270 -> 225
        case 315270:  // 315 -> 270
          offsets = verticalLeft;
          break;
        case 90045:   // 90 -> 45
        case 135090:  // 135 -> 90
        case 225270:  // 225 -> 270
        case 270315:  // 270 -> 315
          offsets = verticalRight;
          break;
        default:
          break;
      }
      for (const auto& offset : offsets) {
        mark(x + offset[0], y + offset[1], 1, bendPriority);
      }
      return;
    }
  };

  for (std::size_t i = 0; i < path.size(); ++i) {
    const int x = path[i][0];
    const int y = path[i][1];
    const int orientation = path[i][2];
    const bool turnsNext = i + 1 < path.size() && path[i][2] != path[i + 1][2];
      markPointFootprint(x,
                         y,
                         orientation,
                         2,
                         turnsNext ? path[i + 1][2] : -1);
    if (i + 1 < path.size()) {
      markInterpolatedStraightSegment(path[i], path[i + 1]);
      if (path[i][2] != path[i + 1][2]) {
        markBendFootprint(path[i], path[i + 1][2]);
      }
    }
  }
}

void LidarDrcManager::deleteNetFromBitmap(const std::string& netName)
{
  auto netIt = _db.netIndex.find(netName);
  if (netIt == _db.netIndex.end()) {
    return;
  }
  auto& net = _db.nets[netIt->second];
  for (const auto& grid : net.rwguide) {
    if (_bitmap.inBounds(grid[0], grid[1])) {
      _bitmap.at(grid[0], grid[1]).deleteNet(netName);
    }
  }
}

void LidarDrcManager::spreadPorts(const std::string& instanceName,
                                  const std::vector<std::size_t>& portIndices,
                                  int orientation)
{
  const int portsNum = static_cast<int>(portIndices.size());
  if (portsNum == 0) {
    return;
  }

  if (portsNum == 1) {
    LidarPort& port = _db.ports[portIndices.front()];
    const std::string name = groupName(instanceName, orientation);
    if (port.netName.has_value()) {
      LidarNet& net = _db.nets[_db.netIndex.at(port.netName.value())];
      const auto& targetPort = _db.ports[net.targetPortIndex];
      const auto& targetInst = _db.instances[_db.instanceIndex.at(targetPort.instanceName)];
      const int portLen = portCountForOrientation(targetInst, targetPort.orientation);
      if (net.sourcePortIndex == portIndices.front() && portLen <= 2) {
        net.reverse = true;
      }
      ensureGroup(_db, name).push_back(port.netName.value());
      net.groups.push_back(name);

      const auto step = orientationStep(port.orientation);
      std::array<int, 2> loc = {truncToInt(port.center.x / _config.gridResolution),
                                truncToInt(port.center.y / _config.gridResolution)};
      while (isBlockage(loc)) {
        loc[0] += step[0];
        loc[1] += step[1];
      }
      for (int i = 0; i < _portLength; ++i) {
        markPortGrid(port, loc);
        loc[0] += step[0];
        loc[1] += step[1];
      }
    }
    return;
  }

  const auto& firstPort = _db.ports[portIndices[0]];
  const auto& secondPort = _db.ports[portIndices[1]];
  const double space = std::abs(firstPort.center.x - secondPort.center.x)
                       + std::abs(firstPort.center.y - secondPort.center.y);

  const int spreadAxis = (orientation == 0 || orientation == 180) ? 1 : 0;
  const int originAxis = (orientation == 0 || orientation == 180) ? 0 : 1;
  std::vector<std::size_t> orderedPorts = portIndices;
  std::stable_sort(orderedPorts.begin(),
                   orderedPorts.end(),
                   [&](std::size_t lhs, std::size_t rhs) {
                     const auto& lp = _db.ports[lhs].center;
                     const auto& rp = _db.ports[rhs].center;
                     const double lv = spreadAxis == 0 ? lp.x : lp.y;
                     const double rv = spreadAxis == 0 ? rp.x : rp.y;
                     return lv < rv;
                   });

  const auto& firstOrdered = _db.ports[orderedPorts.front()];
  const auto& lastOrdered = _db.ports[orderedPorts.back()];
  std::array<int, 2> meanLoc = {
      truncToInt((firstOrdered.center.x + lastOrdered.center.x)
                 / (2.0 * _config.gridResolution)),
      truncToInt((firstOrdered.center.y + lastOrdered.center.y)
                 / (2.0 * _config.gridResolution))};
  const auto step = orientationStep(orientation);
  while (isBlockage(meanLoc)) {
    meanLoc[0] += step[0];
    meanLoc[1] += step[1];
  }

  const std::string name = groupName(instanceName, orientation);
  std::vector<std::string> groupNets;
  const double halfPort = static_cast<double>(portsNum) / 2.0;

  if (std::abs(_config.gridResolution - 1.0) < 1e-9) {
    if (space <= 2.0) {
      const double spreadAxisMin = static_cast<double>(meanLoc[spreadAxis]) - halfPort;
      const double spreadAxisMax = spreadAxisMin + static_cast<double>(portsNum - 1) * 2.0;
      std::vector<int> spreadPoints;
      if (portsNum == 1) {
        spreadPoints.push_back(truncToInt(spreadAxisMin));
      } else {
        const double linStep = (spreadAxisMax - spreadAxisMin)
                               / static_cast<double>(portsNum - 1);
        for (int i = 0; i < portsNum; ++i) {
          spreadPoints.push_back(truncToInt(spreadAxisMin + linStep * i));
        }
      }
      for (int i = 0; i < portsNum; ++i) {
        LidarPort& port = _db.ports[orderedPorts[static_cast<std::size_t>(i)]];
        if (!port.netName.has_value()) {
          continue;
        }
        std::array<int, 2> loc = spreadAxis != 0
                                     ? std::array<int, 2>{meanLoc[originAxis], spreadPoints[i]}
                                     : std::array<int, 2>{spreadPoints[i], meanLoc[originAxis]};
        for (int j = 0; j < _portLength; ++j) {
          markPortGrid(port, loc);
          loc[0] += step[0];
          loc[1] += step[1];
        }
      }
    } else {
      for (int i = 0; i < portsNum; ++i) {
        LidarPort& port = _db.ports[orderedPorts[static_cast<std::size_t>(i)]];
        if (!port.netName.has_value()) {
          continue;
        }
        std::array<int, 2> loc = {truncToInt(port.center.x), truncToInt(port.center.y)};
        loc[0] = meanLoc[0];
        const int portLen
            = i < halfPort ? (i + 1) * _portLength + _radius
                           : (portsNum - i) * _portLength + _radius;
        LidarNet& net = _db.nets[_db.netIndex.at(port.netName.value())];
        net.earlyAccess = true;
        if (net.sourcePortIndex == orderedPorts[static_cast<std::size_t>(i)]) {
          net.reverse = true;
        }
        for (int j = 0; j < portLen; ++j) {
          markPortGrid(port, loc);
          loc[0] += step[0];
          loc[1] += step[1];
        }
      }
    }
    return;
  }

  if (space > _config.gridResolution) {
    for (int i = 0; i < portsNum; ++i) {
      LidarPort& port = _db.ports[orderedPorts[static_cast<std::size_t>(i)]];
      if (!port.netName.has_value()) {
        continue;
      }
      groupNets.push_back(port.netName.value());
      std::array<int, 2> loc = {truncToInt(port.center.x / _config.gridResolution),
                                truncToInt(port.center.y / _config.gridResolution)};
      loc[originAxis] = meanLoc[originAxis];
      int portLen = 0;
      if (portsNum <= 2) {
        portLen = _radius * 4;
      } else if (static_cast<double>(i) < halfPort - 1.0) {
        portLen = i * _portLength + _radius;
      } else if (std::abs(static_cast<double>(i) - (halfPort - 1.0)) < 1e-9) {
        portLen = (i + 1) * _portLength + _radius;
      } else {
        portLen = (portsNum - i - 1) * _portLength + _radius;
      }
      LidarNet& net = _db.nets[_db.netIndex.at(port.netName.value())];
      net.earlyAccess = true;
      net.groups.push_back(name);
      if (net.sourcePortIndex == orderedPorts[static_cast<std::size_t>(i)]
          && instanceName.find("fanout") == std::string::npos) {
        net.reverse = true;
      }
      for (int j = 0; j < portLen; ++j) {
        markPortGrid(port, loc);
        loc[0] += step[0];
        loc[1] += step[1];
      }
    }
    ensureGroup(_db, name) = std::move(groupNets);
    return;
  }

  const int spreadAxisMin =
      truncToInt(static_cast<double>(meanLoc[spreadAxis]) - halfPort);
  const int spreadAxisMax =
      truncToInt(static_cast<double>(meanLoc[spreadAxis]) + halfPort);
  const int sineStep = static_cast<int>(std::ceil(5.0 / _config.gridResolution));
  const int originMean = meanLoc[originAxis];
  int       originSbend = originMean + sineStep * step[0];
  const auto spreadPoints = linspaceInt(spreadAxisMin, spreadAxisMax, portsNum);
  const int originMin = std::min(originMean, originSbend);
  const int originMax = std::max(originMean, originSbend);
  originSbend += step[0];

  if (spreadAxis != 0) {
    for (int j = spreadAxisMin; j <= spreadAxisMax; ++j) {
      if (_bitmap.inBounds(originMin, j)) {
        _bitmap.at(originMin, j).updateBlockage("-1");
      }
      if (_bitmap.inBounds(originMax, j)) {
        _bitmap.at(originMax, j).updateBlockage("-1");
      }
    }
    for (int i = originMin; i < originMax; ++i) {
      if (_bitmap.inBounds(i, spreadAxisMin)) {
        _bitmap.at(i, spreadAxisMin).updateBlockage("-1");
      }
      if (_bitmap.inBounds(i, spreadAxisMax)) {
        _bitmap.at(i, spreadAxisMax).updateBlockage("-1");
      }
    }
  } else {
    for (int j = spreadAxisMin; j <= spreadAxisMax; ++j) {
      if (_bitmap.inBounds(j, originMin)) {
        _bitmap.at(j, originMin).updateBlockage("-1");
      }
      if (_bitmap.inBounds(j, originMax)) {
        _bitmap.at(j, originMax).updateBlockage("-1");
      }
    }
    for (int i = originMin; i < originMax; ++i) {
      if (_bitmap.inBounds(spreadAxisMin, i)) {
        _bitmap.at(spreadAxisMin, i).updateBlockage("-1");
      }
      if (_bitmap.inBounds(spreadAxisMax, i)) {
        _bitmap.at(spreadAxisMax, i).updateBlockage("-1");
      }
    }
  }

  for (int i = 0; i < portsNum; ++i) {
    LidarPort& port = _db.ports[orderedPorts[static_cast<std::size_t>(i)]];
    if (!port.netName.has_value()) {
      continue;
    }
    groupNets.push_back(port.netName.value());
    LidarNet& net = _db.nets[_db.netIndex.at(port.netName.value())];
    net.groups.push_back(name);
    if (net.sourcePortIndex == orderedPorts[static_cast<std::size_t>(i)]
        && instanceName.find("fanout") == std::string::npos) {
      net.reverse = true;
    }
    std::array<int, 2> loc = spreadAxis != 0
                                 ? std::array<int, 2>{originSbend, spreadPoints[i]}
                                 : std::array<int, 2>{spreadPoints[i], originSbend};
    for (int j = 0; j < _portLength; ++j) {
      markPortGrid(port, loc);
      loc[0] += step[0];
      loc[1] += step[1];
    }
  }
  ensureGroup(_db, name) = std::move(groupNets);
}

void writeDrcSummary(const LidarRuntimeView& db,
                     const LidarDrcManager& drc,
                     std::ostream& os)
{
  os << std::fixed << std::setprecision(6);
  const auto counts = drc.bitmap().typeCounts();
  auto countOf = [&](const std::string& key) {
    auto it = counts.find(key);
    return it == counts.end() ? 0 : it->second;
  };

  os << "DRC\twidth=" << drc.bitmapWidth() << "\theight=" << drc.bitmapHeight()
     << "\tradius=" << drc.radius() << "\tport_length=" << drc.portLength()
     << "\tempty=" << countOf("empty") << "\tblk=" << countOf("blk")
     << "\tport=" << countOf("port") << "\tcompound=" << countOf("compound")
     << "\n";

  for (const auto& groupName : db.groupOrder) {
    os << "GROUP\t" << groupName;
    const auto groupIt = db.groupNets.find(groupName);
    if (groupIt == db.groupNets.end()) {
      os << "\n";
      continue;
    }
    for (const auto& netName : groupIt->second) {
      os << "\t" << netName;
    }
    os << "\n";
  }

  for (const auto& net : db.nets) {
    os << "NETSTATE\t" << net.netName << "\treverse=" << (net.reverse ? 1 : 0)
       << "\tearly=" << (net.earlyAccess ? 1 : 0) << "\tgroups=";
    for (std::size_t i = 0; i < net.groups.size(); ++i) {
      if (i != 0) {
        os << ",";
      }
      os << net.groups[i];
    }
    os << "\n";
  }

  for (const auto& port : db.ports) {
    if (port.portGrids.empty()) {
      continue;
    }
    os << "PORTGRID\t" << port.portName << "\tcount=" << port.portGrids.size()
       << "\tfirst=" << port.portGrids.front()[0] << "," << port.portGrids.front()[1]
       << "\tlast=" << port.portGrids.back()[0] << "," << port.portGrids.back()[1]
       << "\n";
  }
}

}  // namespace picpr::lidar
