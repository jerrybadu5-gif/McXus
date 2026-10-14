package pg.mcxus.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import pg.mcxus.app.net.Api
import pg.mcxus.app.net.ApiError
import pg.mcxus.app.net.Session
import pg.mcxus.app.ui.MarketScreen
import pg.mcxus.app.ui.MeScreen
import pg.mcxus.app.ui.OrdersScreen
import pg.mcxus.app.ui.Screen
import pg.mcxus.app.ui.SellScreen
import pg.mcxus.app.ui.SignInScreen
import pg.mcxus.app.ui.Ui
import pg.mcxus.app.ui.Ui.dp
import pg.mcxus.app.ui.WalletScreen
import java.io.IOException

/**
 * The whole app is one Activity with a simple stack of screens and a bottom tab bar.
 * Plain Android views built in Kotlin (no XML layouts, no UI framework), as agreed for the preview.
 */
class MainActivity : Activity() {
    val scope = MainScope()
    lateinit var session: Session
    lateinit var api: Api

    private val stack = ArrayDeque<Screen>()
    private lateinit var titleView: TextView
    private lateinit var backView: TextView
    private lateinit var content: FrameLayout
    private lateinit var tabs: LinearLayout

    /** Called with the result of a photo picker or camera (see SellScreen / ListingScreen). */
    var onActivityResultHandler: ((requestCode: Int, resultCode: Int, data: Intent?) -> Unit)? = null
    var onPermissionHandler: ((granted: Boolean) -> Unit)? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        session = Session(this)
        api = Api(session)
        setContentView(buildFrame())
        if (session.signedIn) openTab(MarketScreen(this)) else show(SignInScreen(this), root = true)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    private fun buildFrame(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFFF6F4EF.toInt())
        }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Ui.GREEN)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        backView = TextView(this).apply {
            text = "‹"
            textSize = 26f
            setTextColor(Color.WHITE)
            setPadding(0, 0, dp(14), 0)
            setOnClickListener { back() }
        }
        titleView = TextView(this).apply {
            textSize = 19f
            setTextColor(Color.WHITE)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        bar.addView(backView)
        bar.addView(titleView)
        content = FrameLayout(this)
        tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.WHITE)
            setPadding(0, dp(4), 0, dp(4))
        }
        listOf(
            "Market" to { MarketScreen(this) },
            "Sell" to { SellScreen(this) },
            "Orders" to { OrdersScreen(this) },
            "Wallet" to { WalletScreen(this) },
            "Me" to { MeScreen(this) },
        ).forEach { (label, make) ->
            tabs.addView(TextView(this).apply {
                text = label
                gravity = Gravity.CENTER
                textSize = 14f
                setTextColor(Ui.GREEN)
                setPadding(0, dp(10), 0, dp(10))
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                setOnClickListener { openTab(make()) }
            })
        }
        root.addView(bar)
        root.addView(content, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(tabs)
        // Android 15 draws apps edge to edge: keep our content clear of the status and navigation bars.
        root.setOnApplyWindowInsetsListener { v, insets ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.ime())
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                    insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        return root
    }

    // ---------- navigation ----------

    fun show(screen: Screen, root: Boolean = false) {
        if (root) stack.clear()
        stack.addLast(screen)
        render()
    }

    fun openTab(screen: Screen) = show(screen, root = true)

    /** Rebuild the current screen (e.g. after an action changed its data). */
    fun refresh() = render()

    fun back() {
        if (stack.size > 1) {
            stack.removeLast()
            render()
        } else {
            finish()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() = back()

    private fun render() {
        val screen = stack.last()
        titleView.text = screen.title
        backView.visibility = if (stack.size > 1) View.VISIBLE else View.GONE
        tabs.visibility = if (screen.showTabs && session.signedIn) View.VISIBLE else View.GONE
        // Screenshot blocking on screens with money or the handover PIN (Android only).
        if (screen.secure) {
            window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        }
        content.removeAllViews()
        content.addView(screen.build())
        screen.load()
    }

    // ---------- background work with friendly errors ----------

    fun launch(block: suspend () -> Unit) {
        scope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                if (e.status == 401) {
                    session.signOut()
                    toast("Please sign in again")
                    show(SignInScreen(this@MainActivity), root = true)
                } else {
                    alert(e.message)
                }
            } catch (e: IOException) {
                alert("Cannot reach the McXus server at ${session.server}.\n\n" +
                    "Check the phone is on the same Wi-Fi as the laptop and the server address is right (Me > Server).")
            } catch (e: Exception) {
                alert(e.message ?: "Something went wrong")
            }
        }
    }

    fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    fun alert(message: String, title: String = "McXus") {
        if (isFinishing) return
        AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("OK", null).show()
    }

    fun confirm(message: String, yes: String = "Yes", onYes: () -> Unit) {
        AlertDialog.Builder(this).setMessage(message)
            .setPositiveButton(yes) { _, _ -> onYes() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        onActivityResultHandler?.invoke(requestCode, resultCode, data)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        onPermissionHandler?.invoke(grantResults.isNotEmpty() && grantResults.all { it == 0 })
    }
}
