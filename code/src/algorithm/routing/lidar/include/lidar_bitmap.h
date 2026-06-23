#pragma once

#include <array>
#include <map>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include "picdb_lidar_view.h"

namespace picpr::lidar
{

enum class BitmapNodeKind
{
  Empty,
  Blockage,
  Port,
  Waveguide,
  Compound
};

struct BitmapNode
{
  BitmapNodeKind kind = BitmapNodeKind::Empty;
  std::optional<int> waveguideType;
  std::string blkID;
  std::vector<std::string> netIDs;
  std::map<std::string, int> wgTypes;
  int length = 0;

  std::string typeString() const;
  void updateEmpty();
  void updateBlockage(const std::string& id);
  void updatePort(const std::string& id);
  void updateWaveguide(const std::string& id, int wgType);
  void deleteNet(const std::string& netName);
};

class Bitmap
{
 public:
  Bitmap() = default;
  Bitmap(const std::vector<LidarPoint>& dieArea,
         double                         resolution,
         int                            distance = 1);

  int width() const { return _width; }
  int height() const { return _height; }
  double resolution() const { return _resolution; }

  bool inBounds(int x, int y) const;
  BitmapNode& at(int x, int y);
  const BitmapNode& at(int x, int y) const;

  void initMap(const std::vector<LidarInstance>& blockages);
  std::unordered_map<std::string, int> typeCounts() const;

 private:
  int _width = 0;
  int _height = 0;
  int _distance = 1;
  double _resolution = 1.0;
  std::vector<BitmapNode> _nodes;
};

}  // namespace picpr::lidar
