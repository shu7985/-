# 记账本（Ledger）— 离线安卓记账 App

Flutter 3.x + Material 3，双录入：手动记账 + 微信/支付宝通知自动记账（进"待确认"）。
数据只存本机 `shared_preferences`（键 `records_v2`），不联网、不申请 INTERNET 权限。

## 一、目录结构

```
scaffold_ledger.py                       一键生成脚本（自包含，所有文件内容内联其中）
.github/workflows/build.yml              GitHub Actions 云打包配置
.gitignore
lib/
  main.dart                              App 入口 / 主题（seed = 0xFF007AFF）
  models/record.dart                     Record 模型 + 枚举 + JSON 序列化
  services/storage.dart                  持久化（load/save，读取失败返回空列表）
  services/payment_listener.dart         通道封装（MethodChannel + EventChannel）
  services/payment_parser.dart           通知文本解析（金额 / 收支 / 商户）
  screens/home_page.dart                 首页：汇总 + 列表 + 去重 + 自动入账
  screens/add_page.dart                  手动记账 / 编辑
  screens/pending_page.dart              待确认列表
android/app/src/main/AndroidManifest.xml
android/app/src/main/kotlin/com/example/ledger/MainActivity.kt
android/app/src/main/kotlin/com/example/ledger/PaymentNotificationService.kt
android/app/build.gradle                 补充：minSdk 21 / targetSdk 34
pubspec.yaml
```

## 二、一键生成脚本（最快路径）

`scaffold_ledger.py` 是自包含的：16 个文件的内容全部内联在里面，不联网、无第三方依赖，
只用 Python 3.7+ 标准库。它会自动建好 `lib/models`、`lib/services`、`lib/screens`、
`android/app/src/main/kotlin/com/example/ledger`、`.github/workflows` 等目录并写入文件。

```bash
# 1. 空目录里生成
mkdir ledger && cd ledger
python scaffold_ledger.py                 # 已存在的文件跳过
python scaffold_ledger.py --force         # 覆盖（会先备份成 .bak）
python scaffold_ledger.py --out myapp     # 指定输出目录
python scaffold_ledger.py --list          # 只打印清单
python scaffold_ledger.py --clean         # 撤销（删掉脚本写出的文件）

# 2. 补 Android 平台壳（gradle wrapper / res / 图标 / debug manifest）
flutter create --org com.example --project-name ledger --platforms=android .

# 3. 把业务代码覆盖回去（flutter create 会写默认的 main.dart / Manifest）
python scaffold_ledger.py --force

# 4. 跑
flutter pub get
flutter run
```

> 顺序很重要：**先 create 后 --force**。反过来也能用，只是 create 可能覆盖掉
> `lib/main.dart` 和 `AndroidManifest.xml`，再跑一次 `--force` 即可。

## 三、本地运行步骤（手动版）

### 1. 生成脚手架

```bash
# 在项目上一级目录执行，--org 决定默认包名，工程名 ledger 会变成 package:ledger
flutter create --org com.example --project-name ledger ledger
cd ledger
```

### 2. 覆盖文件

用本仓库的 `lib/`、`pubspec.yaml`、`android/app/src/main/AndroidManifest.xml`、
`android/app/src/main/kotlin/com/example/ledger/*.kt` 覆盖脚手架里的同名文件。
`flutter create` 会额外生成 `android/app/src/main/kotlin/com/example/ledger/MainActivity.kt`，
直接用本仓库的替换掉。

### 3. 改 minSdk / targetSdk

`android/app/build.gradle`（新版 Flutter 是 `build.gradle.kts`）：

```groovy
defaultConfig {
    minSdk = 21          // 新版 Flutter 默认 24，构建报错就改 24
    targetSdk = 34
}
```

### 4. 安装依赖并运行

```bash
flutter pub get
flutter run            # 连真机，或 flutter run --release
```

> 通知监听在模拟器上也能用，但微信/支付宝通常登不上，建议真机验证自动记账。

### 5. 改包名（可选，题目说你会自己改）

需要同时改 **4 处**，缺一不可：

1. `android/app/build.gradle` 的 `namespace` 和 `applicationId`
2. `android/app/src/main/kotlin/com/example/ledger/` 这个**目录路径**（挪到新包路径下）
3. `MainActivity.kt` 和 `PaymentNotificationService.kt` 里的 `package com.example.ledger`
4. 重装时先 `flutter clean`

Manifest 里的 `.MainActivity` / `.PaymentNotificationService` 是相对写法，不用改。

也可以一条命令搞定（保险起见先备份）：

```bash
flutter pub run change_app_package_name:main com.yourname.ledger
```

### 6. 手机开启"通知使用权"

1. 首次启动 App 会弹窗，点"去开启"（或点 AppBar 右上的小铃铛图标）
2. 系统路径一般是：**设置 → 通知与状态栏 → 通知使用权 / 通知监听**
   （部分 ROM：设置 → 应用 → 特殊应用权限 → 通知使用权）
3. 在列表里找到「记账本」，打开开关，弹窗确认"允许"
4. 回 App，铃铛图标消失即成功

验证自动记账：

```bash
adb logcat -s PayNotif          # 只看通知原文
adb logcat -s flutter           # 看 Dart 侧 [自动记账] 日志
```

用微信/支付宝付 0.01 元 → Logcat 出现 `raw = ...` → App 首页出现一条黄色「待确认」。

### 7. 打包

```bash
flutter build apk --release
# 产物：build/app/outputs/flutter-apk/app-release.apk

# 按 ABI 拆分（体积更小）
flutter build apk --release --split-per-abi
```

## 四、云端打包（GitHub Actions）

`.github/workflows/build.yml` 已配好，push 即可自动出包，不用本地装 Flutter/Android SDK。

```bash
git init && git add . && git commit -m "feat: 记账本"
git remote add origin git@github.com:<你的账号>/<仓库名>.git
git push -u origin main
```

流程：`checkout` → JDK 17 → Flutter 3.24.5（固定版本保证可重现）→
`flutter create` 生成 Android 壳 → `python3 scaffold_ledger.py --force` 写业务代码 →
`pub get` → `flutter analyze`（仅告警，不阻塞）→ `build apk --release` →
上传 `ledger-release-apk`。

在 Actions 页面点进任意一次 run，底部 **Artifacts** 就能下载 APK。
也支持网页手动触发（workflow_dispatch）和打 tag（`v1.0.0`）。

- 想把版本换成最新：把 `flutter-version: '3.24.5'` 删掉，只留 `channel: stable`
- 想要按 ABI 拆分小包：`flutter build apk --release --split-per-abi`
- 想签正式包：把 keystore 放进 GitHub Secrets 并在 `android/app/build.gradle` 里引用

## 五、已知限制与下一步优化

**1. 通知文案会变，正则一定会漂移。**
微信/支付宝的通知文案随版本、灰度、机型（尤其 MIUI/ColorOS 的折叠通知）不同而不同。
`payment_parser.dart` 的金额正则和关键词需要拿真机 `PayNotif` 日志反复校准。
解析不出来时**故意返回 null 不入账**，不会瞎猜错账。

**2. App 进程被杀时，自动记账会"只打日志不入库"。**
`NotificationListenerService` 是系统保活的，但 Flutter 引擎不在时 `EventSink` 为空，
事件只能写 Logcat。想彻底解决需要：前台服务 + 本地缓存队列（原生侧先落盘，Dart 启动时回灌）。

**3. 去重是内存级、30 秒时间桶的粗粒度方案。**
同一笔支付若在 30 秒后被重复推送仍会重复入账；App 重启后 Set 清空。更稳的做法是把
`source + 金额 + 通知时间去重`落盘，或用 `StatusBarNotification.getKey()` 做唯一键回传。

**4. 存储是全量 JSON，条目多了会慢。**
`shared_preferences` 每次保存都要序列化整表，几千条以后首页会有可感知的卡顿。
下一步换 `sqflite` / `drift`，配合分页查询。

**5. 自动记账不推断分类。**
分类直接填商户名（如"星巴克"），需要用户手动改成"餐饮"。
可以加一层商户→分类的本地映射表，命中就自动归类。

**6. 缺统计报表。**
目前只有总收入/总支出/结余。下一步：按月分组、分类饼图、预算提醒、CSV 导出/备份。

## 六、验收自测清单

- [ ] `flutter pub get` 无依赖冲突
- [ ] `flutter run` 启动，手动记一笔支出/收入 → 列表 + 汇总正确
- [ ] 左滑删除 → 有撤销
- [ ] 杀掉 App 重开 → 数据仍在
- [ ] 开启通知使用权 → 付 0.01 元 → Logcat 有 `PayNotif` → 待确认多一条
- [ ] 待确认里"确认入账" → 黄色标签消失、计入汇总；"全部确认"生效
- [ ] `flutter build apk --release` 出包，装到手机上仍能自动记账
