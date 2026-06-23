#pragma once

#include <array>
#include <iosfwd>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "lidar_bitmap.h"
#include "picdb_lidar_view.h"

namespace picpr::lidar
{

struct LidarDrcConfig
{
  double gridResolution = 2.0;
  double bendRadius = 5.0;
  int maxCrossing = 10;
};

struct LidarDrcNode
{
  std::array<int, 3>      pos = {0, 0, 0};
  int                     crossingBudget = 0;
  int                     straightCount = 0;
  bool                    violated = false;
  std::set<std::string>   violatedNets;
};

struct LidarDrcStep
{
  int         dx = 0;
  int         dy = 0;
  int         orientation = 0;
  std::string type;
};

struct LidarDrcCheck
{
  bool                      violated = false;
  std::string               type = "empty";
  std::optional<int>        waveguideType;
  std::optional<std::string> netName;
};

struct LidarDrcResult
{
  bool                               violated = false;
  std::optional<std::array<int, 3>>  crossingNeighbor;
  std::string                        resultType;
  std::set<std::string>              violatedNets;
  std::optional<std::string>         crossingNet;
};

class LidarDrcManager
{
 public:
  LidarDrcManager(LidarRuntimeView& db, const LidarDrcConfig& config);

  void initDRC();
  void initBitmap();
  void initPorts();
  void spreadPorts(const std::string& instanceName,
                   const std::vector<std::size_t>& portIndices,
                   int orientation);
  LidarDrcCheck checkSingleNode(const std::array<int, 3>& index,
                                const std::string& checkNet = "") const;
  LidarDrcCheck checkSingleNode(int x,
                                int y,
                                const std::string& checkNet = "") const;
  int checkSpacing(const std::array<int, 3>& node,
                   int checkRegion,
                   const std::set<std::string>& groups = {}) const;
  LidarDrcResult bViolateDRC(const LidarDrcNode& currentNode,
                             const LidarDrcStep& step,
                             bool crossingEnable,
                             const std::string& netName,
                             bool enablePrediction) const;
  void updatePathBitmap(const std::vector<std::array<int, 3>>& path,
                        const std::string& netName);
  void deleteNetFromBitmap(const std::string& netName);

  Bitmap& bitmap() { return _bitmap; }
  const Bitmap& bitmap() const { return _bitmap; }
  int bitmapWidth() const { return _bitmap.width(); }
  int bitmapHeight() const { return _bitmap.height(); }
  int portLength() const { return _portLength; }
  int radius() const { return _radius; }
  int bend45Part1() const { return _bend45Part1; }
  int bend45Part2() const { return _bend45Part2; }
  int predictLength() const { return _predictLength; }
  void setRoutingBendParameters(int bend90,
                                int bend45Part1,
                                int bend45Part2,
                                int predictLength);

 private:
  std::array<int, 2> orientationStep(double orientation) const;
  std::array<int, 2> checkStep(int orientation) const;
  int orientationBucket(double orientation) const;
  int portCountForOrientation(const LidarInstance& instance, double orientation) const;
  std::vector<int> linspaceInt(int start, int stop, int count) const;
  void markPortGrid(LidarPort& port, const std::array<int, 2>& loc);
  bool isBlockage(const std::array<int, 2>& loc) const;
  bool crossingCheck(const LidarNet& host,
                     const LidarNet& slave,
                     int straightCount,
                     bool manhattan,
                     double& halfSize) const;

  LidarRuntimeView& _db;
  LidarDrcConfig _config;
  Bitmap _bitmap;
  int _radius = 0;
  int _bend45Part1 = 3;
  int _bend45Part2 = 2;
  int _predictLength = 3;
  int _portLength = 0;
};

void writeDrcSummary(const LidarRuntimeView& db,
                     const LidarDrcManager& drc,
                     std::ostream& os);

}  // namespace picpr::lidar
