package pg.mcxus.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import pg.mcxus.app.chat.ChatEngine
import pg.mcxus.app.chat.Incoming
import pg.mcxus.app.chat.Payload

/**
 * New-message notifications, made on the phone after it decrypts the message (the push itself is empty).
 * On the lock screen Android shows only "New message" unless the person allows sensitive content there.
 */
object Notifier {
    private const val CHANNEL = "messages"

    fun createChannel(context: Context) {
        val channel = NotificationChannel(CHANNEL, "Messages", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "New chat messages"
            lockscreenVisibility = android.app.Notification.VISIBILITY_PRIVATE
        }
        context.getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
    }

    fun allowed(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    fun show(context: Context, app: App, engine: ChatEngine, incoming: Incoming) {
        if (!allowed(context)) return
        if (app.inForeground && app.openChat == incoming.conversationId) return
        val conv = engine.conversation(incoming.conversationId)
        val show = app.session.showPreviews
        val title = if (show) conv?.name ?: "McXus" else "McXus"
        val preview = if (show) Payload.preview(incoming.message.payload) else "New message"
        val open = PendingIntent.getActivity(
            context, incoming.conversationId.hashCode(),
            Intent(context, MainActivity::class.java).putExtra(MainActivity.EXTRA_CHAT, incoming.conversationId)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val public = android.app.Notification.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle("McXus").setContentText("New message").build()
        val notification = android.app.Notification.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFF0B2545.toInt())
            .setContentTitle(title)
            .setContentText(preview)
            .setStyle(android.app.Notification.BigTextStyle().bigText(preview))
            .setCategory(android.app.Notification.CATEGORY_MESSAGE)
            .setVisibility(android.app.Notification.VISIBILITY_PRIVATE)
            .setPublicVersion(public)
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        context.getSystemService(NotificationManager::class.java)?.notify(incoming.conversationId.hashCode(), notification)
    }

    /** A dispute needs my answer (new dispute, an offer, a decision). Tap opens the dispute. */
    fun showDispute(context: Context, app: App, orderId: String, title: String, what: String) {
        if (!allowed(context)) return
        val show = app.session.showPreviews
        val open = PendingIntent.getActivity(
            context, ("dispute:$orderId").hashCode(),
            Intent(context, MainActivity::class.java).putExtra(MainActivity.EXTRA_DISPUTE, orderId)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val public = android.app.Notification.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle("McXus").setContentText("A dispute needs your answer").build()
        val text = if (show) "$title: $what" else "A dispute needs your answer"
        val notification = android.app.Notification.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFF0B2545.toInt())
            .setContentTitle(if (show) "Dispute" else "McXus")
            .setContentText(text)
            .setStyle(android.app.Notification.BigTextStyle().bigText(text))
            .setVisibility(android.app.Notification.VISIBILITY_PRIVATE)
            .setPublicVersion(public)
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        context.getSystemService(NotificationManager::class.java)?.notify(("dispute:$orderId").hashCode(), notification)
    }

    fun clear(context: Context, conversationId: String) {
        context.getSystemService(NotificationManager::class.java)?.cancel(conversationId.hashCode())
    }
}
