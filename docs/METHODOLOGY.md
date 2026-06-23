# C++ LiDAR Router Methodology

本文总结本次 C++ 化 LiDAR 布线器的实际方法。目标不是写一个能跑的演示器，而是把 Python 原版 LiDAR 的功能迁移成速度更快、结果接近或等于人工/标准 GDS 的 C++ 布线器。

## 一、总体路线

核心策略是“语义等价优先，性能优化第二”。不要一开始就重写一个看起来合理的布线器，否则很容易得到 DRC 干净但和标准结果差很远的 GDS。

推荐流程：

1. 固定输入 benchmark 和标准结果。
2. 能跑通 Python 原版，得到 Python 原始结果。
3. 给 Python 原版加 trace dump，记录每条 net 的关键中间状态。
4. C++ 实现相同数据模型、bitmap、DRC、A*、post-process。
5. 逐层比较 C++ 与 Python：origin path、processed path、crossing set、post path、GDS。
6. 再和标准 GDS 比较：bbox、cell count、layer area、XOR、hotspot。
7. 确认问题在哪一层，再修那一层。

## 二、输入与数据模型

LiDAR benchmark 输入是 YAML，不是已经布线好的 GDS。输入里主要有：

```text
instances
placements
ports
nets
settings
```

官方 `*.layout.yml` 里虽然有 layout 字样，但 `routes: {}`、`connections: {}`、`nets: []`，不能当作标准布线答案。

C++ 数据模型需要保留这些信息：

1. die area。
2. component bbox。
3. instance orientation。
4. port name、port center、orientation、width。
5. source/target net。
6. group 信息。
7. crossing budget、crossing nets、routing order。

对应代码：

```text
code/src/algorithm/routing/lidar/include/picdb_lidar_view.h
code/src/algorithm/routing/lidar/src/picdb_lidar_view.cpp
code/src/algorithm/routing/lidar/include/lidar_router.h
```

## 三、DRC bitmap

LiDAR 的核心不是简单几何绕障，而是把 photonic routing 约束离散到 bitmap 上。

bitmap 里要区分：

```text
empty
blk
port
compound
waveguide
```

重要经验：bitmap 初始化必须和 Python 原版完全一致。一个整数截断、`abs()`、inclusive range 的差异，都会让 access grid 偏移，最后 GDS 大面积不同。

本次关键修复：

```text
xmin = int(abs(blk.bbox.lx - distance) / resolution)
xmax = int(abs(blk.bbox.ux + distance) / resolution)
ymin = int(abs(blk.bbox.ly - distance) / resolution)
ymax = int(abs(blk.bbox.uy + distance) / resolution)
```

对应代码：

```text
code/src/algorithm/routing/lidar/src/lidar_bitmap.cpp
code/src/algorithm/routing/lidar/src/lidar_drc.cpp
```

## 四、Port Access

port access 不是简单从端口中心拉一条线。Python LiDAR 会根据端口朝向、端口数量、bend radius、port length、是否分组等因素生成 access grids。

需要对齐的点：

1. 单 port 的直线 access。
2. 多 port 的 spread access。
3. close-port S-bend spread。
4. group reverse 情况。
5. `meanLoc` 遇 blockage 的推进方式。
6. access grid 是否标记为 port 或 blockage。

本次修复重点：

```text
while (isBlockage(meanLoc)) {
    meanLoc += step;
}
```

并去掉 C++ 初版里额外的 widening/other-blockage 特殊行为，让它更接近 Python 原版。

## 五、A* 搜索

C++ LiDAR 的 A* 状态不是二维坐标，而是：

```text
x
y
orientation
crossing_budget
crossing_net
```

代价函数包含：

```text
propagation loss
bending loss
crossing loss
congestion/history cost
spacing penalty
illegal crossing penalty
```

neighbor 类型包括：

```text
straight
bend_45_1
bend_45_2
bend_90
crossing_0
crossing_45
Sbend_x
Sbend_y
```

对应代码：

```text
code/src/algorithm/routing/lidar/src/lidar_astar.cpp
```

## 六、Crossing-aware Routing

高质量 photonic routing 不能简单禁止所有交叉。某些 case，特别是 MMI，需要合理使用 optical crossing 才能得到接近人工布线的结果。

算法思路：

1. 允许 crossing budget。
2. A* 遇到已有 waveguide 时判断是否可插入 crossing。
3. 记录 crossing net。
4. 先尝试带 crossing 的路径。
5. 再尝试 no-crossing detour。
6. 用插入损耗比较两种路径。
7. 必要时 rip-up crossing 相关 net。

核心原则：

```text
crossing 不是错误，它是受控资源。
uncontrolled crossing 才是错误。
```

## 七、Rip-up / Reroute / History

复杂 case 一次 A* 通常不够。需要全局流程：

1. 按 net order 或 topology order 布线。
2. route 失败时放松 DRC 或启用 fallback。
3. 如果 crossing route 代价不合理，尝试 no-crossing route。
4. 如果 no-crossing 失败，rip-up 相关 crossing nets。
5. 重布局部冲突区域。
6. 用 history map 惩罚反复拥塞点。

对应代码：

```text
routeAllNetsGrid()
routeSingleNetGrid()
routeWithPythonPolicy()
```

## 八、Post-processing

GDS 差异经常不是 A* 路径错，而是 post-processing 错。需要把粗略 grid path 转成 gdsfactory 能接受的 photonic route。

关键步骤：

1. 删除 collinear 冗余点。
2. 根据 source/target port 做方向对齐。
3. 把 grid path 转成 micron path。
4. 对 crossing nets 做路径相交检测。
5. split 两条 crossing path。
6. 插入 crossing cell。
7. 生成 crossing ports。
8. 修短连接段。
9. 输出 post paths。

本次 MMI 剩余 XOR 主要就在这一层。

## 九、GDS 渲染

GDS 渲染使用 Python `gdsfactory/kfactory`。这部分必须固定版本，否则同一条路径会生成不同 cell name、metadata、via array 或 crossing geometry。

本次标准 GDS metadata 显示：

```text
kfactory 2.4.6
klayout 0.30.6
```

因此最终对齐环境使用固定的 GDS-render 依赖：

```text
gdsfactory==9.40.2
kfactory==2.4.6
klayout==0.30.6
```

对应脚本：

```text
code/tools/pr_lidar_native/scripts/render_route_result_gds.py
```

## 十、验证体系

不要只看 GDS viewer。viewer 只能告诉你肉眼像不像，不能证明几何一致。

推荐验证顺序：

1. `route_success=true`。
2. DRC `clean=1`。
3. 路径数量、crossing 数量一致。
4. Python vs C++ origin path 一致。
5. Python vs C++ post path 接近或一致。
6. 标准 GDS vs C++ GDS bbox 一致。
7. layer area 接近。
8. XOR 为 0 或足够小。
9. 检查 XOR hotspot。
10. 检查 runtime。

本次标准三例最终结果：

```text
clements_8x8:        XOR 0.000000
multiportmmi_8x8:    XOR 5.091752
multiportmmi_16x16:  XOR 18.680864
```

## 十一、性能方法

速度提升主要来自：

1. A* 搜索从 Python 迁到 C++。
2. bitmap 查询、DRC 查询变成 C++ 内存访问。
3. Python set 的行为用 C++ 容器模拟，但保持 deterministic order。
4. 路由核心和 GDS 渲染分离。
5. 回归脚本只调用 native binary，不反复初始化 Python router。

目前瓶颈：

```text
YAML conversion
gdsfactory render
KLayout/GDS write
large MMI A* search
```

下一步优化可以考虑：

1. 把 YAML 转换迁到 C++。
2. 把部分 GDS route object 生成迁到 C++。
3. 对 A* open set、visited map、history map 做 cache/locality 优化。
4. 对 group routes 做更强的并行或局部并行。

## 十二、硬编码边界

允许：

```text
benchmark list in regression script
standard file names in compare script
version-specific compatibility in renderer
general geometric tolerance
```

不允许：

```text
按 case 名写固定路径
读取标准 GDS 再复制 geometry 到输出
根据标准 XOR hotspot 手工补 polygon
为某个 net id 写专用绕线规则
```

本次 C++ 结果不是复制标准 GDS。哈希、文件大小、cell count 均不同；标准 GDS 只在 compare 脚本中通过参数或环境变量用于验证。
