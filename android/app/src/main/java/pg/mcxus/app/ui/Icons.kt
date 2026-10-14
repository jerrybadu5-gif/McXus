package pg.mcxus.app.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/** Line icons drawn from the same SVG paths as the approved design (24 x 24, 2 px stroke). No icon library. */
object Ic {
    private fun circle(cx: Float, cy: Float, r: Float) = "M${cx - r} ${cy}a$r $r 0 1 0 ${2 * r} 0a$r $r 0 1 0 ${-2 * r} 0Z"
    private fun rect(x: Float, y: Float, w: Float, h: Float, r: Float) =
        "M${x + r} ${y}h${w - 2 * r}a$r $r 0 0 1 $r ${r}v${h - 2 * r}a$r $r 0 0 1 ${-r} ${r}h${-(w - 2 * r)}" +
            "a$r $r 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a$r $r 0 0 1 $r ${-r}Z"

    private fun line(name: String, vararg paths: String, width: Float = 2f) =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).apply {
            paths.forEach {
                addPath(
                    pathData = addPathNodes(it),
                    stroke = SolidColor(Color.Black),
                    strokeLineWidth = width,
                    strokeLineCap = StrokeCap.Round,
                    strokeLineJoin = StrokeJoin.Round,
                )
            }
        }.build()

    private fun solid(name: String, vararg paths: String, size: Float = 24f) =
        ImageVector.Builder(name, 24.dp, 24.dp, size, size).apply {
            paths.forEach { addPath(pathData = addPathNodes(it), fill = SolidColor(Color.Black)) }
        }.build()

    val Chat = line("chat", "M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z")
    val NewChat = line("newchat", "M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z", "M12 8v8M8 12h8", width = 2.2f)
    val Discover = line("discover", circle(12f, 12f, 9f), "m15.5 8.5-2 5-5 2 2-5 5-2Z")
    val Market = line("market", "M4 9h16l-1 11H5L4 9Z", "M9 9V7a3 3 0 0 1 6 0v2")
    val Wallet = line("wallet", rect(3f, 6f, 18f, 14f, 3f), "M3 10h18M16 15h2")
    val Me = line("me", circle(12f, 8f, 4f), "M4 21a8 8 0 0 1 16 0")
    val Search = line("search", circle(11f, 11f, 7f), "m20 20-3.5-3.5")
    val Scan = line("scan", "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M7 12h10")
    val Back = line("back", "m15 5-7 7 7 7", width = 2.2f)
    val Lock = line("lock", rect(5f, 11f, 14f, 10f, 2f), "M8 11V7a4 4 0 0 1 8 0v4")
    val Shield = line("shield", "M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z", "m9 12 2 2 4-4")
    val Plus = line("plus", "M12 5v14M5 12h14", width = 2.4f)
    val Send = line("send", "M4 12 20 4l-4 16-4-6-8-2Z", "m12 14 8-10")
    val Pin = line("pin", "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Z", circle(12f, 10f, 2.5f))
    val Down = line("down", "m6 9 6 6 6-6", width = 2.2f)
    val Right = line("right", "m9 6 6 6-6 6", width = 2.2f)
    val Heart = line("heart", "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z")
    val Share = line("share", "M4 12v7h16v-7M12 3v12M7 8l5-5 5 5")
    val Eye = line("eye", "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z", circle(12f, 12f, 3f))
    val Bell = line("bell", "M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2ZM10 21h4")
    val Qr = line("qr", "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 18h2v2h-2z")
    val Receipt = line("orders", "M6 3h12v18l-3-2-3 2-3-2-3 2V3Z", "M9 8h6M9 12h6")
    val Camera = line("photo", rect(3f, 7f, 18f, 13f, 3f), "M8 7l2-3h4l2 3", circle(12f, 13.5f, 3.5f))
    val Refresh = line("refresh", "M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7")
    val Logout = line("logout", "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3", "M10 17l-5-5 5-5M5 12h11")
    val Server = line("server", rect(4f, 4f, 16f, 7f, 2f), rect(4f, 13f, 16f, 7f, 2f), "M8 7.5h.01M8 16.5h.01")
    val Up = line("topup", "M12 19V5M5 12l7-7 7 7")
    val Out = line("withdraw", "M12 5v14M5 12l7 7 7-7")
    val Swap = line("send stars", "M7 7h13l-4-4M17 17H4l4 4")
    val Edit = line("edit", "M4 20h4L20 8l-4-4L4 16v4Z")
    val Store = line("store", "M4 10v10h16V10M3 10l2-6h14l2 6H3Z", "M10 20v-5h4v5")
    val Play = solid("play", "M7 4v16l13-8Z")
    val More = solid("more", circle(12f, 5f, 1.8f), circle(12f, 12f, 1.8f), circle(12f, 19f, 1.8f))
    val Check = line("check", "m5 12 5 5 9-10", width = 2.4f)
    val DoubleCheck = line("read", "m2 13 4 4 8-9M10 16l1 1 9-10", width = 2.2f)
    val Mic = line("mic", rect(9f, 3f, 6f, 11f, 3f), "M5 11a7 7 0 0 0 14 0M12 18v3")

    val Group = line("group", circle(9f, 8f, 3.5f), "M2.5 20a6.5 6.5 0 0 1 13 0", circle(17f, 9f, 2.5f), "M16 14.2A5 5 0 0 1 21.5 19")
    val Image = line("image", rect(3f, 4f, 18f, 16f, 3f), circle(9f, 10f, 2f), "m21 16-5-5-9 9")
    val Stop = solid("stop", "M7 7h10v10H7z")
    val Pause = solid("pause", "M7 5h3.5v14H7zM13.5 5H17v14h-3.5z")
    val Close = line("close", "M6 6l12 12M18 6 6 18", width = 2.4f)
    val PinSolid = solid("pin", "M12 2a8 8 0 0 0-8 8c0 5.6 7 11.6 7.3 11.9a1 1 0 0 0 1.4 0C13 21.6 20 15.6 20 10a8 8 0 0 0-8-8Zm0 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6Z")
    val Locate = line("locate", circle(12f, 12f, 7f), circle(12f, 12f, 2.5f), "M12 2v3M12 19v3M2 12h3M19 12h3")

    /** The eight-point McXus Star (also the currency mark for Stars). Fill colour comes from the caller. */
    val Star = solid("star", "M54,8 L62,40 L96,32 L71,54 L96,76 L62,68 L54,100 L46,68 L12,76 L37,54 L12,32 L46,40 Z", size = 108f)
}
