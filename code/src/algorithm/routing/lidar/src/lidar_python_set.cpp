#include "picdb_lidar_view.h"

#include <algorithm>
#include <limits>

namespace picpr::lidar
{

namespace
{

std::uint64_t readLittleEndian64(const char* data)
{
  std::uint64_t value = 0;
  for (int i = 0; i < 8; ++i) {
    value |= static_cast<std::uint64_t>(
                 static_cast<unsigned char>(data[i]))
             << (8 * i);
  }
  return value;
}

std::uint64_t rotateLeft64(std::uint64_t value, int shift)
{
  return (value << shift) | (value >> (64 - shift));
}

void sipRound13(std::uint64_t& v0,
                std::uint64_t& v1,
                std::uint64_t& v2,
                std::uint64_t& v3)
{
  v0 += v1;
  v1 = rotateLeft64(v1, 13);
  v1 ^= v0;
  v0 = rotateLeft64(v0, 32);
  v2 += v3;
  v3 = rotateLeft64(v3, 16);
  v3 ^= v2;
  v0 += v3;
  v3 = rotateLeft64(v3, 21);
  v3 ^= v0;
  v2 += v1;
  v1 = rotateLeft64(v1, 17);
  v1 ^= v2;
  v2 = rotateLeft64(v2, 32);
}

std::uint64_t pythonHashSeed0Bits(const std::string& value)
{
  if (value.empty()) {
    return 0;
  }
  std::uint64_t v0 = 0x736f6d6570736575ULL;
  std::uint64_t v1 = 0x646f72616e646f6dULL;
  std::uint64_t v2 = 0x6c7967656e657261ULL;
  std::uint64_t v3 = 0x7465646279746573ULL;

  const char* data = value.data();
  std::size_t offset = 0;
  while (offset + 8 <= value.size()) {
    const std::uint64_t mi = readLittleEndian64(data + offset);
    v3 ^= mi;
    sipRound13(v0, v1, v2, v3);
    v0 ^= mi;
    offset += 8;
  }

  std::uint64_t tail = static_cast<std::uint64_t>(value.size()) << 56;
  for (std::size_t i = 0; offset + i < value.size(); ++i) {
    tail |= static_cast<std::uint64_t>(
                static_cast<unsigned char>(data[offset + i]))
            << (8 * i);
  }
  v3 ^= tail;
  sipRound13(v0, v1, v2, v3);
  v0 ^= tail;
  v2 ^= 0xff;
  for (int i = 0; i < 3; ++i) {
    sipRound13(v0, v1, v2, v3);
  }
  std::uint64_t hash = v0 ^ v1 ^ v2 ^ v3;
  if (hash == std::numeric_limits<std::uint64_t>::max()) {
    hash = static_cast<std::uint64_t>(-2LL);
  }
  return hash;
}

std::size_t nextPowerOfTwoSetSize(std::size_t used)
{
  std::size_t newSize = 8;
  const std::size_t minUsed = used > 50000 ? used * 2 : used * 4;
  while (newSize <= minUsed) {
    newSize <<= 1;
  }
  return newSize;
}

std::size_t findSlot(const std::vector<LidarPythonStringSet::Slot>& slots,
                     const std::string& value,
                     std::uint64_t hash,
                     bool forInsert,
                     bool& found)
{
  constexpr int perturbShift = 5;
  constexpr std::size_t linearProbes = 9;
  const std::size_t mask = slots.size() - 1;
  std::size_t index = static_cast<std::size_t>(hash) & mask;
  std::uint64_t perturb = hash;
  std::size_t firstDummy = slots.size();

  while (true) {
    const std::size_t probeCount =
        (index + linearProbes <= mask) ? linearProbes : 0;
    for (std::size_t offset = 0; offset <= probeCount; ++offset) {
      const auto slotIndex = index + offset;
      const auto& slot = slots[slotIndex];
      if (slot.state == LidarPythonStringSet::SlotState::Empty) {
        found = false;
        return (forInsert && firstDummy != slots.size()) ? firstDummy
                                                         : slotIndex;
      }
      if (slot.state == LidarPythonStringSet::SlotState::Dummy) {
        if (forInsert && firstDummy == slots.size()) {
          firstDummy = slotIndex;
        }
      } else if (slot.hash == hash && slot.value == value) {
        found = true;
        return slotIndex;
      }
    }
    perturb >>= perturbShift;
    index = (index * 5 + 1 + static_cast<std::size_t>(perturb)) & mask;
  }
}

void insertSlotNoResize(LidarPythonStringSet& set, const std::string& value)
{
  const auto hash = pythonHashSeed0Bits(value);
  bool found = false;
  const auto slotIndex = findSlot(set.slots, value, hash, true, found);
  if (found) {
    return;
  }
  auto& slot = set.slots[slotIndex];
  if (slot.state == LidarPythonStringSet::SlotState::Empty) {
    ++set.fill;
  }
  slot.state = LidarPythonStringSet::SlotState::Occupied;
  slot.value = value;
  slot.hash = hash;
  ++set.used;
}

void resizeSlots(LidarPythonStringSet& set, std::size_t newSize)
{
  std::vector<std::string> oldValues;
  oldValues.reserve(set.used);
  for (const auto& slot : set.slots) {
    if (slot.state == LidarPythonStringSet::SlotState::Occupied) {
      oldValues.push_back(slot.value);
    }
  }

  set.slots.assign(newSize, LidarPythonStringSet::Slot{});
  set.used = 0;
  set.fill = 0;
  for (const auto& value : oldValues) {
    insertSlotNoResize(set, value);
  }
}

}  // namespace

LidarPythonStringSet::LidarPythonStringSet()
    : slots(8)
{
}

LidarPythonStringSet::LidarPythonStringSet(
    const std::set<std::string>& initialValues)
    : LidarPythonStringSet()
{
  for (const auto& value : initialValues) {
    insert(value);
  }
}

bool LidarPythonStringSet::insert(const std::string& value)
{
  const auto hash = pythonHashSeed0Bits(value);
  bool found = false;
  const auto slotIndex = findSlot(slots, value, hash, true, found);
  if (found) {
    return false;
  }

  auto& slot = slots[slotIndex];
  if (slot.state == SlotState::Empty) {
    ++fill;
  }
  slot.state = SlotState::Occupied;
  slot.value = value;
  slot.hash = hash;
  ++used;
  values.insert(value);

  const auto mask = slots.size() - 1;
  if (fill * 5 >= mask * 3) {
    resizeSlots(*this, nextPowerOfTwoSetSize(used));
  }
  return true;
}

std::size_t LidarPythonStringSet::erase(const std::string& value)
{
  const auto hash = pythonHashSeed0Bits(value);
  bool found = false;
  const auto slotIndex = findSlot(slots, value, hash, false, found);
  if (!found) {
    return 0;
  }

  auto& slot = slots[slotIndex];
  slot.state = SlotState::Dummy;
  slot.value.clear();
  slot.hash = 0;
  --used;
  values.erase(value);
  return 1;
}

void LidarPythonStringSet::clear()
{
  values.clear();
  slots.assign(8, Slot{});
  used = 0;
  fill = 0;
}

bool LidarPythonStringSet::empty() const
{
  return values.empty();
}

std::size_t LidarPythonStringSet::size() const
{
  return values.size();
}

std::size_t LidarPythonStringSet::count(const std::string& value) const
{
  return values.count(value);
}

const std::set<std::string>& LidarPythonStringSet::sortedValues() const
{
  return values;
}

std::vector<std::string> LidarPythonStringSet::pythonIterationOrder() const
{
  std::vector<std::string> ordered;
  ordered.reserve(values.size());
  for (const auto& slot : slots) {
    if (slot.state == SlotState::Occupied) {
      ordered.push_back(slot.value);
    }
  }
  return ordered;
}

LidarPythonStringSet::const_iterator LidarPythonStringSet::begin() const
{
  return values.begin();
}

LidarPythonStringSet::const_iterator LidarPythonStringSet::end() const
{
  return values.end();
}

}  // namespace picpr::lidar
