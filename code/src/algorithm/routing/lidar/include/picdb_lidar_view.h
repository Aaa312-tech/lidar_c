#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <iosfwd>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include "design.h"

namespace picpr::lidar {

// LiDAR's router needs Python-compatible per-port/net routing state
// (bitmap grids, crossing bookkeeping, routed paths).  PIC-DB Design remains
// the source of truth; this view is rebuilt from Design for one routing run and
// should not be treated as a second persistent database.

struct LidarPoint
{
  double x = 0.0;
  double y = 0.0;
};

// Python LiDAR stores crossing_nets as a CPython set.  Post-processing depends
// on that set's deterministic slot iteration order when PYTHONHASHSEED=0,
// including tombstones left by remove().  This runtime-only container keeps a
// normal sorted set for stable reporting/membership and a Python-compatible
// slot table for the routing algorithm.
struct LidarPythonStringSet
{
  enum class SlotState
  {
    Empty,
    Occupied,
    Dummy,
  };

  struct Slot
  {
    SlotState     state = SlotState::Empty;
    std::string   value;
    std::uint64_t hash = 0;
  };

  using const_iterator = std::set<std::string>::const_iterator;

  LidarPythonStringSet();
  explicit LidarPythonStringSet(const std::set<std::string>& initialValues);

  bool insert(const std::string& value);
  std::size_t erase(const std::string& value);
  void clear();
  bool empty() const;
  std::size_t size() const;
  std::size_t count(const std::string& value) const;
  const std::set<std::string>& sortedValues() const;
  std::vector<std::string> pythonIterationOrder() const;

  const_iterator begin() const;
  const_iterator end() const;

  std::set<std::string> values;
  std::vector<Slot>     slots;
  std::size_t           used = 0;
  std::size_t           fill = 0;
};

struct LidarBox
{
  double lx = 0.0;
  double ly = 0.0;
  double ux = 0.0;
  double uy = 0.0;
};

struct LidarPinDefinition
{
  std::string name;
  double      offsetX     = 0.0;
  double      offsetY     = 0.0;
  double      width       = 0.0;
  double      orientation = 0.0;
  int         layer       = 1;
};

struct LidarMacro
{
  std::string                                  name;
  double                                       iloss = 0.0;
  std::string                                  type  = "CORE";
  LidarPoint                                   origin;
  double                                       sizeX = 0.0;
  double                                       sizeY = 0.0;
  std::string                                  site  = "core";
  std::vector<LidarPinDefinition>              pins;
  std::unordered_map<std::string, std::size_t> pinIndex;
};

struct LidarPort
{
  std::string                     portName;
  std::string                     instanceName;
  std::string                     pinName;
  LidarPoint                      center;
  double                          width       = 0.0;
  double                          orientation = 0.0;
  std::optional<std::string>      netName;
  std::vector<std::array<int, 2>> portGrids;
  int                             idBlk = -1;
};

struct LidarInstance
{
  std::string                             name;
  std::string                             component;
  std::string                             macroType;
  std::string                             placementStatus;
  std::string                             orientation;
  LidarPoint                              lowerLeft;
  LidarBox                                bbox;
  int                                     idBlk = -1;
  std::array<double, 4>                   halo  = {10.0, 10.0, 10.0, 10.0};
  std::array<std::vector<std::size_t>, 4> portsByOrientation;
};

struct LidarNet
{
  std::string netName;
  std::string designNetName;
  int         netID = -1;

  int  failedCount = 0;
  bool enable45    = true;
  bool routed      = false;

  std::set<std::array<int, 2>>    rwguide;
  std::vector<std::array<int, 3>> routedPath;
  std::vector<std::array<int, 3>> originPath;
  std::vector<std::array<int, 4>> rectRoute;
  bool                            shortSbend = false;
  double                          shortSbendLength = 0.0;
  std::vector<std::string>        groups;
  std::optional<std::string>      groupName;

  std::string sourcePortName;
  std::string targetPortName;
  std::size_t sourcePortIndex = 0;
  std::size_t targetPortIndex = 0;
  bool        reverse         = false;
  bool        earlyAccess     = false;

  double      width      = 0.5;
  int         wavelength = 143;
  std::string material   = "WG";
  double      halfSize   = 5.0;

  int                   topologyCrossing = 0;
  int                   maximumCrossing  = 0;
  int                   crossingBudget   = 100;
  int                   currentBudget    = 100;
  LidarPythonStringSet  crossingNets;

  int                   vionets = 0;
  std::set<std::string> vioNets;

  double insertionLoss = 0.0;
  double wirelength    = 0.0;
  double bending       = 0.0;
  int    crossingNum   = 0;

  double eulerDistance = 0.0;
  double compDist      = 0.0;
  int    routingOrder  = 0;
};

struct LidarRuntimeView
{
  std::string                                               designName;
  std::vector<LidarPoint>                                   dieArea;
  std::vector<LidarMacro>                                   macros;
  std::vector<LidarInstance>                                instances;
  std::vector<LidarPort>                                    ports;
  std::vector<LidarNet>                                     nets;
  std::vector<std::vector<std::string>>                     topologyOrders;
  std::vector<std::string>                                  groupOrder;
  std::unordered_map<std::string, std::vector<std::string>> groupNets;
  std::unordered_map<std::string, LidarNet>                 abnormalNets;
  std::unordered_map<std::string, std::size_t>              macroIndex;
  std::unordered_map<std::string, std::size_t>              instanceIndex;
  std::unordered_map<std::string, std::size_t>              portIndex;
  std::unordered_map<std::string, std::size_t>              netIndex;
};

struct LidarViewOptions
{
  bool                  preserveOriginalNetNames = false;
  bool                  deterministicOrder       = false;
  bool                  snapNearIntegerCoordinates = false;
  std::string           generatedNetPrefix       = "n_";
  std::array<double, 4> defaultHalo              = {10.0, 10.0, 10.0, 10.0};
};

std::string placementToString(Placement placement);
std::string orientationFromCell(const Cell& cell);
std::string componentNameForLidar(const std::string& picdbType);

LidarRuntimeView buildRuntimeViewFromDesign(
    const Design& design,
    const LidarViewOptions& options = LidarViewOptions());

void writeRuntimeViewSummary(const LidarRuntimeView& view, std::ostream& os);

}  // namespace picpr::lidar
