// android/app/src/main/kotlin/com/example/ledger/PaymentNotificationService.kt
//
// 通知监听服务：只关心微信（com.tencent.mm）和支付宝（com.eg.android.AlipayGphone）。
// 拿到通知后把 title / text / bigText / textLines / raw 一股脑通过 EventChannel
// 推给 Flutter，解析（金额、收支方向、商户）全部在 Dart 侧做。
//
// 调试：Logcat 过滤 tag = PayNotif，能看到每条原始文本。
//
// 注意：本 Service 只负责"捞原文"，不做任何判断，避免原生侧和 Dart 侧逻辑重复。

package com.example.ledger

import android.app.Notification
import android.os.Handler
import android.os.Looper
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import io.flutter.plugin.common.EventChannel

class PaymentNotificationService : NotificationListenerService() {

    companion object {
        private const val TAG = "PayNotif"

        /**
         * 只处理这两个包。
         * TODO: 如果以后要接其它支付渠道（如云闪付 unionpay），在这里加映射即可，
         *       同时在 Dart 侧 PaymentParser 里补关键词。
         */
        private val TARGET_PACKAGES = mapOf(
            "com.tencent.mm" to "wechat",
            "com.eg.android.AlipayGphone" to "alipay"
        )

        /**
         * Flutter 侧的 EventSink。由 MainActivity 的 EventChannel onListen 赋值。
         * 用 @Volatile 保证跨线程可见性；Service 回调在 Binder 线程，发送要切主线程。
         */
        @Volatile
        var eventSink: EventChannel.EventSink? = null

        private val mainHandler = Handler(Looper.getMainLooper())
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.d(TAG, "通知监听已连接，可以开始抓微信/支付宝通知了")
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        Log.d(TAG, "通知监听已断开（可能被系统回收或用户关闭了开关）")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val notification = sbn ?: return
        val pkg = notification.packageName ?: return

        // 1) 包名过滤：不是微信/支付宝直接返回，不产生任何开销
        val source = TARGET_PACKAGES[pkg] ?: return

        val extras = notification.notification?.extras ?: return

        // 2) 提取各字段（全部做空安全处理，取不到就是空串）
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val lines: List<String> = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)
            ?.map { it?.toString().orEmpty() }
            ?: emptyList()

        val raw = listOf(title, text, bigText, lines.joinToString(" / "))
            .filter { it.isNotBlank() }
            .joinToString(" | ")

        // 3) 打日志，方便用 Logcat 校准 Dart 侧正则
        Log.d(TAG, "---- 收到 $pkg ($source) ----")
        Log.d(TAG, "title   = $title")
        Log.d(TAG, "text    = $text")
        Log.d(TAG, "bigText = $bigText")
        Log.d(TAG, "lines   = $lines")
        Log.d(TAG, "raw     = $raw")

        if (raw.isBlank()) {
            Log.d(TAG, "文本为空（可能是纯图标通知），跳过")
            return
        }

        // 4) 组装 payload
        val payload = HashMap<String, Any?>()
        payload["source"] = source
        payload["packageName"] = pkg
        payload["title"] = title
        payload["text"] = text
        payload["bigText"] = bigText
        payload["lines"] = lines
        payload["raw"] = raw
        payload["timestamp"] = notification.postTime   // 毫秒时间戳
        payload["notificationId"] = notification.id

        val sink = eventSink
        if (sink == null) {
            // Flutter 引擎没起来（App 被杀 / 还没订阅），只留日志。
            // 这是当前架构的已知限制，见 README 的"已知限制"。
            Log.d(TAG, "Flutter 侧未监听，本次只记录日志")
            return
        }

        // 5) EventSink 必须在主线程调用
        mainHandler.post {
            try {
                eventSink?.success(payload)
            } catch (e: Exception) {
                Log.e(TAG, "推送事件到 Flutter 失败: ${e.message}", e)
            }
        }
    }

    // 通知被移除时不用管，这里留个空实现说明一下（不覆盖也能跑）
    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        // no-op
    }
}
