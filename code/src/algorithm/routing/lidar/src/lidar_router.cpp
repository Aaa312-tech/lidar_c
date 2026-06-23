#include "lidar_router.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <ostream>
#include <utility>

namespace picpr::lidar
{

namespace
{

double cross(const LidarPoint& a, const LidarPoint& b, const LidarPoint& c)
{
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

bool inRange(double value, double lower, double upper)
{
  constexpr double eps = 1e-9;
  return value + eps >= std::min(lower, upper) && value - eps <= std::max(lower, upper);
}

bool netLess(const LidarNet& lhs, const LidarNet& rhs)
{
  return (lhs.compDist < rhs.compDist)
         || (lhs.compDist == rhs.compDist && lhs.routingOrder < rhs.routingOrder);
}

}  // namespace

LidarGridRouter::LidarGridRouter(LidarRuntimeView& db, LidarRouteConfig config)
    : _db(db), _config(std::move(config))
{
}

bool LidarGridRouter::segmentsIntersect(const LidarPoint& a,
                                        const LidarPoint& b,
                                        const LidarPoint& c,
                                        const LidarPoint& d) const
{
  constexpr double eps = 1e-9;
  const double c1 = cross(a, b, c);
  const double c2 = cross(a, b, d);
  const double c3 = cross(c, d, a);
  const double c4 = cross(c, d, b);

  if (std::abs(c1) <= eps && inRange(c.x, a.x, b.x) && inRange(c.y, a.y, b.y)) {
    return true;
  }
  if (std::abs(c2) <= eps && inRange(d.x, a.x, b.x) && inRange(d.y, a.y, b.y)) {
    return true;
  }
  if (std::abs(c3) <= eps && inRange(a.x, c.x, d.x) && inRange(a.y, c.y, d.y)) {
    return true;
  }
  if (std::abs(c4) <= eps && inRange(b.x, c.x, d.x) && inRange(b.y, c.y, d.y)) {
    return true;
  }

  return ((c1 > eps && c2 < -eps) || (c1 < -eps && c2 > eps))
         && ((c3 > eps && c4 < -eps) || (c3 < -eps && c4 > eps));
}

int LidarGridRouter::processNetOrder()
{
  if (_config.netOrder != "topo") {
    return 0;
  }

  int crossingCount = 0;
  for (std::size_t level = 0; level < _db.topologyOrders.size(); ++level) {
    std::vector<std::string> routedLineNames;
    routedLineNames.reserve(_db.topologyOrders[level].size());

    for (const auto& netName : _db.topologyOrders[level]) {
      auto netIt = _db.netIndex.find(netName);
      if (netIt == _db.netIndex.end()) {
        continue;
      }

      LidarNet& net = _db.nets[netIt->second];
      net.compDist = static_cast<double>(level);
      const LidarPort& source = _db.ports[net.sourcePortIndex];
      const LidarPort& target = _db.ports[net.targetPortIndex];

      for (const auto& lineName : routedLineNames) {
        LidarNet& priorNet = _db.nets[_db.netIndex.at(lineName)];
        const LidarPort& priorSource = _db.ports[priorNet.sourcePortIndex];
        const LidarPort& priorTarget = _db.ports[priorNet.targetPortIndex];
        if (segmentsIntersect(source.center, target.center, priorSource.center, priorTarget.center)) {
          ++net.topologyCrossing;
          ++priorNet.topologyCrossing;
          ++crossingCount;
        }
      }
      routedLineNames.push_back(netName);
    }
  }
  return crossingCount;
}

std::vector<std::string> LidarGridRouter::globalPriorityOrder() const
{
  std::vector<std::size_t> heap;
  heap.reserve(_db.nets.size());

  auto lessIndex = [&](std::size_t lhs, std::size_t rhs) {
    return netLess(_db.nets[lhs], _db.nets[rhs]);
  };
  auto siftdown = [&](std::vector<std::size_t>& h, std::size_t startPos, std::size_t pos) {
    const auto newItem = h[pos];
    while (pos > startPos) {
      const std::size_t parentPos = (pos - 1) >> 1;
      const auto parent = h[parentPos];
      if (lessIndex(newItem, parent)) {
        h[pos] = parent;
        pos = parentPos;
        continue;
      }
      break;
    }
    h[pos] = newItem;
  };
  auto siftup = [&](std::vector<std::size_t>& h, std::size_t pos) {
    const std::size_t endPos = h.size();
    const std::size_t startPos = pos;
    const auto newItem = h[pos];
    std::size_t childPos = 2 * pos + 1;
    while (childPos < endPos) {
      const std::size_t rightPos = childPos + 1;
      if (rightPos < endPos && !lessIndex(h[childPos], h[rightPos])) {
        childPos = rightPos;
      }
      h[pos] = h[childPos];
      pos = childPos;
      childPos = 2 * pos + 1;
    }
    h[pos] = newItem;
    siftdown(h, startPos, pos);
  };
  auto heappush = [&](std::vector<std::size_t>& h, std::size_t index) {
    h.push_back(index);
    siftdown(h, 0, h.size() - 1);
  };
  auto heappop = [&](std::vector<std::size_t>& h) {
    const auto lastItem = h.back();
    h.pop_back();
    if (h.empty()) {
      return lastItem;
    }
    const auto returnItem = h.front();
    h.front() = lastItem;
    siftup(h, 0);
    return returnItem;
  };

  for (std::size_t i = 0; i < _db.nets.size(); ++i) {
    if (!_db.nets[i].routed) {
      heappush(heap, i);
    }
  }

  std::vector<std::string> order;
  order.reserve(heap.size());
  while (!heap.empty()) {
    const auto index = heappop(heap);
    order.push_back(_db.nets[index].netName);
  }
  return order;
}

void writeRouteInitSummary(LidarRuntimeView& db,
                           const LidarRouteConfig& config,
                           std::ostream& os)
{
  os << std::fixed << std::setprecision(6);
  LidarGridRouter router(db, config);
  const int crossingCount = router.processNetOrder();
  os << "ROUTEINIT\tnet_order=" << config.netOrder << "\tgroup=" << (config.group ? 1 : 0)
     << "\tCR=" << crossingCount << "\n";

  for (const auto& net : db.nets) {
    os << "ROUTENET\t" << net.netName << "\tcomp=" << net.compDist
       << "\trouting_order=" << net.routingOrder
       << "\ttopology_crossing=" << net.topologyCrossing << "\n";
  }

  os << "GLOBALPQ";
  for (const auto& netName : router.globalPriorityOrder()) {
    os << "\t" << netName;
  }
  os << "\n";
}

}  // namespace picpr::lidar
