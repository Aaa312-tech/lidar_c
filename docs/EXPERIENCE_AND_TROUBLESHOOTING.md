# Experience And Troubleshooting

本文总结本次 C++ LiDAR 布线器开发中最常见的问题、定位方法和处理经验。

## 1. 输入看起来像 layout，但不是标准布线结果

现象：

```text
*.layout.yml 存在
但没有 route
```

判断方法：

```yaml
connections: {}
routes: {}
ports: {}
nets: []
```

结论：这是 layout/placement/component 描述，不是已经布好线的标准结果。

## 2. 肉眼一样不等于 GDS 一样

GDS viewer 缩放级别有限，几平方微米的差异肉眼看不出来。

必须用：

```text
compare_gds_geometry.py
gds_pair_summary.csv
gds_layer_xor.csv
gds_xor_hotspots.csv
```

例子：

```text
multiportmmi_8x8:
  viewer 看起来一样
  XOR = 5.091752 um^2
```

## 3. 文件一样要看 hash，不要靠视觉判断

如果怀疑输出是复制标准 GDS，检查：

```powershell
Get-FileHash -Algorithm SHA256 <file.gds>
```

复制文件必须同时满足：

```text
file size identical
hash identical
cell count identical
```

本次三个结果都不是标准 GDS 的直接复制。

## 4. 标准 GDS 版本环境会影响结果

同一条 route path，用不同 gdsfactory/kfactory 版本可能生成不同 GDS：

```text
cell name 不同
metadata 不同
crossing cell 不同
via array 不同
polygon discretization 不同
```

本次标准 GDS metadata 指向：

```text
kfactory 2.4.6
klayout 0.30.6
```

所以最终渲染环境使用：

```text
gdsfactory 9.40.2
kfactory 2.4.6
klayout 0.30.6
```

## 5. bitmap off-by-one 会造成大面积差异

现象：

```text
DRC 可能还是 clean
但 GDS 和 Python/标准差很多
origin path 大量不同
```

常见原因：

```text
floor vs trunc
round vs int
inclusive loop vs exclusive loop
bbox +/- distance 顺序错
abs() 行为没对齐 Python
```

处理方法：

1. dump Python origin path。
2. dump C++ origin path。
3. 逐 net 比较 grid sequence。
4. 先修 bitmap，再修 A*。

## 6. port access 是高风险区域

现象：

```text
路径主体接近
但端口附近出现绕线差异
或者短连接 DRC
```

常见原因：

```text
port_length 不一致
meanLoc 推进方式不一致
group reverse 不一致
close-port S-bend 规则不一致
端口 orientation 被旋转后没有正确转换
```

处理方法：

1. 输出 port grid summary。
2. 对齐 Python `DrcManager.spreadPorts()`。
3. 不要为了某个 case 加额外避障逻辑，先确认 Python 是否真的这么做。

## 7. crossing split 不要过早 snap

现象：

```text
MMI 路由大体正确
crossing 附近 XOR 小但不为 0
```

原因：

```text
intersection 点被提前 snap 到 0.001um
split path 使用了 access-inclusive path
crossing center 由不同 port 反推时有 1e-6um 差异
```

处理经验：

1. split 用原始交点。
2. crossing center 保持原始 double。
3. 渲染时允许极小容差聚类。
4. 不要随意删除 short connector repair。

## 8. 删除一个修复可能让 XOR 变小，但 DRC 变差

本次试过删除 `repairShortCrossingConnector()`：

```text
局部 XOR 有改善
但 multiportmmi_8x8 出现 DRC marker
```

经验：不能只按 XOR 优化。最终目标顺序应该是：

```text
先 DRC clean
再 geometry close
最后 XOR zero
```

## 9. layer44 via array 差异不一定是路由错

现象：

```text
clements 路径完全一致
但标准 XOR 仍然很大
差异集中在 layer44
```

原因：

```text
不同 gdsfactory/kfactory 版本生成的 via array 不同
旧环境 4x4
标准环境 5x5
```

解决：

```text
切换到与标准 metadata 一致的锁定 GDS-render 环境
```

## 10. Python 原版结果不一定等于标准 GDS

本次发现：

```text
当前 Python 原版 + 旧环境生成的 GDS
并不等于用户提供的标准 GDS
```

说明标准 GDS 可能来自更具体的版本组合或生成流程。不要把“当前 Python 能跑出的结果”自动当作 golden。

## 11. MRR case 当前仍有风险

当前 `results/reference_run` 归档中：

```text
mrr_weight_bank_4x4: clean
mrr_weight_bank_8x8: 2 markers
mrr_weight_bank_16x16: 86 markers
```

主要问题：

```text
waveguide_crossing
waveguide_overlap
部分 crossing component overlap
```

处理建议：

1. 单独为 MRR 打开 route dump。
2. 找 marker 对应 net。
3. 比较 Python old env、C++ raw path、C++ post path。
4. 优先修 crossing post-process，不要先改 A* cost。

## 12. 遇到难题时的定位顺序

推荐固定流程：

```text
1. 先确认输入是否一致。
2. 检查 layout bbox、component bbox、port center。
3. 比较 bitmap init summary。
4. 比较 port grids。
5. 比较 origin_path_grid。
6. 比较 crossing_nets。
7. 比较 post_paths。
8. 比较 GDS layer area。
9. 看 XOR hotspot。
10. 再决定改哪一层。
```

不要直接在最终 GDS 层面猜原因。

## 13. 好的改法和坏的改法

好的改法：

```text
对齐 Python 原版语义
使用通用几何规则
用 trace 证明修改点
每次修改后跑 DRC 和 XOR
保留失败实验结果
```

坏的改法：

```text
按 case 名特殊处理
按 net id 特殊处理
为了 XOR 牺牲 DRC
复制标准 GDS geometry
只看 viewer 不看 XOR
```

## 14. 本次最重要的经验

1. C++ 化不是翻译语法，而是复制算法语义。
2. 高质量 photonic routing 的难点在 port access 和 crossing post-process。
3. 版本环境是几何结果的一部分。
4. GDS exactness 要靠层级验证，不靠肉眼。
5. 不要一次修太多层。每层都要有可比较的中间产物。
