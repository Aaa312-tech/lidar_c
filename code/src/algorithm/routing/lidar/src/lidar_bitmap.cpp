#include "lidar_bitmap.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace picpr::lidar
{

std::string BitmapNode::typeString() const
{
  switch (kind) {
    case BitmapNodeKind::Empty:
      return "empty";
    case BitmapNodeKind::Blockage:
      return "blk";
    case BitmapNodeKind::Port:
      return "port";
    case BitmapNodeKind::Compound:
      return "compound";
    case BitmapNodeKind::Waveguide:
      return waveguideType.has_value() ? std::to_string(waveguideType.value())
                                       : "waveguide";
  }
  return "empty";
}

void BitmapNode::updateEmpty()
{
  if (kind == BitmapNodeKind::Blockage || kind == BitmapNodeKind::Port) {
    return;
  }
  kind = BitmapNodeKind::Empty;
  waveguideType.reset();
  netIDs.clear();
  wgTypes.clear();
  length = 0;
}

void BitmapNode::updateBlockage(const std::string& id)
{
  kind = BitmapNodeKind::Blockage;
  waveguideType.reset();
  blkID = id;
}

void BitmapNode::updatePort(const std::string& id)
{
  if (kind == BitmapNodeKind::Empty) {
    kind = BitmapNodeKind::Port;
    waveguideType.reset();
    blkID = id;
  }
}

void BitmapNode::updateWaveguide(const std::string& id, int wgType)
{
  if (kind == BitmapNodeKind::Blockage || kind == BitmapNodeKind::Port) {
    return;
  }
  netIDs.push_back(id);
  wgTypes[id] = wgType;
  ++length;
  if (length > 1) {
    kind = BitmapNodeKind::Compound;
    waveguideType.reset();
  } else {
    kind = BitmapNodeKind::Waveguide;
    waveguideType = wgType;
  }
}

void BitmapNode::deleteNet(const std::string& netName)
{
  if (kind == BitmapNodeKind::Blockage || kind == BitmapNodeKind::Port) {
    return;
  }
  auto it = wgTypes.find(netName);
  if (it == wgTypes.end()) {
    return;
  }
  if (kind == BitmapNodeKind::Compound) {
    // Upstream LiDAR only deletes the active wgtype entry for compound cells.
    // Its netID list intentionally keeps stale entries until the cell collapses
    // back to one live waveguide, and A* congestion checks read netID[0].
    wgTypes.erase(it);
    --length;
    if (length == 1 && !wgTypes.empty()) {
      kind = BitmapNodeKind::Waveguide;
      for (const auto& id : netIDs) {
        auto remaining = wgTypes.find(id);
        if (remaining != wgTypes.end()) {
          waveguideType = remaining->second;
          netIDs = {remaining->first};
          break;
        }
      }
    }
    return;
  }
  wgTypes.erase(it);
  netIDs.erase(std::remove(netIDs.begin(), netIDs.end(), netName), netIDs.end());
  length = 0;
  kind = BitmapNodeKind::Empty;
  waveguideType.reset();
  netIDs.clear();
}

Bitmap::Bitmap(const std::vector<LidarPoint>& dieArea,
               double                         resolution,
               int                            distance)
    : _distance(distance), _resolution(resolution)
{
  if (dieArea.size() < 2) {
    throw std::runtime_error("LiDAR bitmap requires a two-point die area");
  }
  _width = static_cast<int>(
      std::round((dieArea[1].x - dieArea[0].x) / _resolution));
  _height = static_cast<int>(
      std::round((dieArea[1].y - dieArea[0].y) / _resolution));
  if (_width <= 0 || _height <= 0) {
    throw std::runtime_error("Invalid LiDAR bitmap dimensions");
  }
  _nodes.resize(static_cast<std::size_t>(_width) * static_cast<std::size_t>(_height));
}

bool Bitmap::inBounds(int x, int y) const
{
  return x >= 0 && y >= 0 && x < _width && y < _height;
}

BitmapNode& Bitmap::at(int x, int y)
{
  if (!inBounds(x, y)) {
    throw std::out_of_range("LiDAR bitmap index out of bounds");
  }
  return _nodes[static_cast<std::size_t>(x) * static_cast<std::size_t>(_height)
                + static_cast<std::size_t>(y)];
}

const BitmapNode& Bitmap::at(int x, int y) const
{
  if (!inBounds(x, y)) {
    throw std::out_of_range("LiDAR bitmap index out of bounds");
  }
  return _nodes[static_cast<std::size_t>(x) * static_cast<std::size_t>(_height)
                + static_cast<std::size_t>(y)];
}

void Bitmap::initMap(const std::vector<LidarInstance>& blockages)
{
  for (const auto& blk : blockages) {
    const int xmin = static_cast<int>(std::abs(blk.bbox.lx - _distance) / _resolution);
    const int xmax = static_cast<int>(std::abs(blk.bbox.ux + _distance) / _resolution);
    const int ymin = static_cast<int>(std::abs(blk.bbox.ly - _distance) / _resolution);
    const int ymax = static_cast<int>(std::abs(blk.bbox.uy + _distance) / _resolution);
    for (int x = xmin; x <= xmax; ++x) {
      for (int y = ymin; y <= ymax; ++y) {
        if (inBounds(x, y)) {
          at(x, y).updateBlockage(blk.name);
        }
      }
    }
  }
}

std::unordered_map<std::string, int> Bitmap::typeCounts() const
{
  std::unordered_map<std::string, int> counts;
  for (const auto& node : _nodes) {
    ++counts[node.typeString()];
  }
  return counts;
}

}  // namespace picpr::lidar
