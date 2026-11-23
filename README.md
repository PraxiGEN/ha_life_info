# <img src="custom_components/life_info/brand/icon.png" width="64"> 🏠 生活信息 (Life Info)

[![Release](https://img.shields.io/github/v/release/PraxiGEN/ha_life_info)](https://github.com/PraxiGEN/ha_life_info/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/PraxiGEN/ha_life_info/blob/main/LICENSE)
[![Marketplace](https://img.shields.io/badge/Marketplace-Available-blue.svg)](https://www.hacs.xyz/docs/marketplace/)

## 🏠 本地生活助手合集：把多个本地生活服务收拢到同一个集成里，一次安装，统一配置入口。

## ✨ 核心特性

### 🎯 一个集成，多个服务
- **合集式实现**：所有服务在同一个集成内落地，共用配置入口、协调器、实体平台、选项框架与持久化层；新增服务只需在其私有包里补齐取数 / 界面 / 实体清单，用户侧不用多装一个集成。
- **一条目多设备**：每个服务一个条目，户号或省份作为设备挂在同一条目下；服务级唯一，重复添加直接拒绝。

### 📋 服务支持列表

| 服务 | 提供的信息 | 数据来源 | 认证 | 设备粒度 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **昆仑燃气** | 表端/账户余额、欠费、账单气费、表读数、表具通信、是否可缴费（7 个实体） | 中国石油网上营业厅公开接口 | 免密（户号 + 地区） | 每户号一台设备 | ✅ 已支持 |
| **油价信息** | 92/95/98 号汽油、0 号柴油省级价格 + 独立调价信息实体（5 个实体） | xxapi / ApiZero / 网页 | 免密（ApiZero KEY 选填） | 每省份一台设备 | ✅ 已支持 |

> 想接入新的生活服务？欢迎通过 Issue 提出建议。

### 🔌 免密优先
- 服务优先接入无需认证信息的公开数据源：昆仑燃气仅需户号 + 地区，油价主源完全免 KEY。
- ApiZero KEY 为可选增强（匿名每日 5 次，填写后每日 20 次），只影响调价预测获取，不参与主价格源。

### 🔄 容错与降级
- **油价三级冗余**：价格按 xxapi → ApiZero → 网页逐级回补；三源全失败才抛更新失败、实体转不可用，下个周期自动重试。
- **燃气缓存兜底**：取数失败在 24 小时 TTL 内沿用缓存应对短期抖动；过期仍失败则标记不可用，避免无限期展示陈旧数据。
- **调价信息独立缓存**：ApiZero 调价信息 24 小时缓存，跨重启保留，失败不影响价格实体。

## 📦 安装

### 通过自定义存储库添加（推荐）

> 自 Home Assistant **2026.11** 起，HACS 已内置为系统自带的 **市场（Marketplace）**，位于 **设置 > 市场**；更早版本请先独立安装 [HACS](https://www.hacs.xyz/)。

**操作步骤：**

1. 打开 Home Assistant，进入 **设置 > 市场**，点击右上角 **⋮ 菜单 > 自定义存储库**
2. 仓库地址填入：
```yaml
https://github.com/PraxiGEN/ha_life_info
```
3. 类别选择 **集成（Integration）**，点击 **添加**
4. 回到市场搜索 **“生活信息”**（或 `Life Info`），进入详情页点击 **安装**
5. 安装完成后进入配置向导，选择服务并填写接入信息即可使用

> 安装后**无需重启**：集成带配置向导，安装完成即加载并直接引导你完成配置。只有在更新已安装的集成后，系统才会提示重启（按提示操作即可）。

### 手动安装（离线/无市场环境）

1. 下载最新的 Release：
```yaml
https://github.com/PraxiGEN/ha_life_info
```
2. 解压并将 `custom_components/life_info` 文件夹放入 Home Assistant 的 `custom_components` 目录
3. 重启 Home Assistant
4. 前往 **设置 > 设备与服务 > 添加集成**，搜索 **生活信息** 完成配置

## 📖 文档导航
- [🚀 详细配置与使用教程 (DOCS.md)](md/DOCS.md)
- [📜 版本更新历史 (CHANGELOG.md)](md/CHANGELOG.md)

## 🤝 贡献

欢迎贡献代码、报告问题或提出功能建议！

1. 提交Issues：报告问题或功能请求（欢迎提出想接入的生活信息服务）
2. 提交Pull Requests：贡献代码改进
3. 项目讨论：分享使用经验或建议

## 📄 许可证

本项目基于MIT许可证开源。详情请查看LICENSE文件。

## ❤️ 支持

如果这个项目对您有帮助，请给项目点个Star ⭐！

## 📜 免责声明

本集成提供的燃气账单与油价数据来自公开接口，仅供生活信息参考，不作为计费结算、交易决策或安全判断依据。实际金额请以服务方官方账单为准。

---

## 兼容版本:

- **Home Assistant 2026.9.0+**
