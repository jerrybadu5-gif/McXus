package pg.mcxus.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.SnackbarHost
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import pg.mcxus.app.ui.screens.ChatScreen
import pg.mcxus.app.ui.screens.DisputeScreen
import pg.mcxus.app.ui.screens.DisputesListScreen
import pg.mcxus.app.ui.screens.FrozenScreen
import pg.mcxus.app.ui.screens.HomeScreen
import pg.mcxus.app.ui.screens.ListingScreen
import pg.mcxus.app.ui.screens.GroupInfoScreen
import pg.mcxus.app.ui.screens.NewChatScreen
import pg.mcxus.app.ui.screens.NewGroupScreen
import pg.mcxus.app.ui.screens.OrderScreen
import pg.mcxus.app.ui.screens.OrdersScreen
import pg.mcxus.app.ui.screens.ProfileScreen
import pg.mcxus.app.ui.screens.SellScreen
import pg.mcxus.app.ui.screens.SignInScreen
import pg.mcxus.app.ui.theme.McXusTheme
import pg.mcxus.app.ui.theme.Mx

/** One Activity; every screen is Jetpack Compose. */
class MainActivity : ComponentActivity() {
    private lateinit var app: App

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.WHITE, android.graphics.Color.WHITE),
        )
        super.onCreate(savedInstanceState)
        app = (application as McXusApp).app
        if (app.signedIn) app.startChat()
        pendingChat.value = target(intent)
        setContent {
            McXusTheme {
                CompositionLocalProvider(LocalApp provides app) { Root(pendingChat) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        pendingChat.value = target(intent)
    }

    override fun onStart() {
        super.onStart()
        app.inForeground = true
        app.usedNow()
    }

    override fun dispatchTouchEvent(ev: android.view.MotionEvent): Boolean {
        if (ev.actionMasked == android.view.MotionEvent.ACTION_DOWN) app.usedNow()
        return super.dispatchTouchEvent(ev)
    }

    override fun onStop() {
        app.inForeground = false
        super.onStop()
    }

    /** Chat to open when the person taps a notification. */
    private val pendingChat = mutableStateOf<String?>(null)

    companion object {
        const val EXTRA_CHAT = "chat"
        const val EXTRA_DISPUTE = "dispute"

        /** Where a tapped notification leads: a chat id, or "dispute:<order id>". */
        fun target(intent: Intent?): String? =
            intent?.getStringExtra(EXTRA_DISPUTE)?.let { "dispute:$it" } ?: intent?.getStringExtra(EXTRA_CHAT)
    }
}

object Routes {
    const val SIGN_IN = "signin"
    const val HOME = "home"
    fun chat(id: String) = "chat/$id"
    fun listing(id: String) = "listing/$id"
    fun order(id: String) = "order/$id"
    fun dispute(orderId: String) = "dispute/$orderId"
    const val DISPUTES = "disputes"
    const val NEW_CHAT = "newchat"
    const val NEW_GROUP = "newgroup"
    fun group(id: String) = "group/$id"
    const val SELL = "sell"
    const val ORDERS = "orders"
    const val PROFILE = "profile"
}

@Composable
private fun Root(pendingChat: MutableState<String?>) {
    val app = LocalApp.current
    val nav = rememberNavController()
    LaunchedEffect(app.signedIn) {
        if (!app.signedIn) nav.navigate(Routes.SIGN_IN) { popUpTo(0) }
    }
    LaunchedEffect(pendingChat.value, app.signedIn) {
        val target = pendingChat.value ?: return@LaunchedEffect
        if (app.signedIn) nav.navigate(if (target.startsWith("dispute:")) Routes.dispute(target.removePrefix("dispute:")) else Routes.chat(target))
        pendingChat.value = null
    }
    if (app.signedIn && app.frozen) {
        Box(Modifier.fillMaxSize()) {
            FrozenScreen()
            MessageHost(app, Modifier.align(Alignment.BottomCenter))
        }
        return
    }
    Box(Modifier.fillMaxSize()) {
        NavHost(nav, startDestination = if (app.signedIn) Routes.HOME else Routes.SIGN_IN, modifier = Modifier.imePadding()) {
            composable(Routes.SIGN_IN) { SignInScreen(onDone = { nav.navigate(Routes.HOME) { popUpTo(0) } }) }
            composable(Routes.HOME) { HomeScreen(nav) }
            composable("chat/{id}") { ChatScreen(nav, it.arguments?.getString("id")!!) }
            composable("listing/{id}") { ListingScreen(nav, it.arguments?.getString("id")!!) }
            composable("order/{id}") { OrderScreen(nav, it.arguments?.getString("id")!!) }
            composable("dispute/{id}") { DisputeScreen(nav, it.arguments?.getString("id")!!) }
            composable(Routes.DISPUTES) { DisputesListScreen(nav) }
            composable(Routes.NEW_CHAT) { NewChatScreen(nav) }
            composable(Routes.NEW_GROUP) { NewGroupScreen(nav) }
            composable("group/{id}") { GroupInfoScreen(nav, it.arguments?.getString("id")!!) }
            composable(Routes.SELL) { SellScreen(nav) }
            composable(Routes.ORDERS) { OrdersScreen(nav) }
            composable(Routes.PROFILE) { ProfileScreen(nav) }
        }
        MessageHost(app, Modifier.align(Alignment.BottomCenter))
    }
}

/** Messages sit just above the keyboard when it is open, otherwise above the tab bar. Errors are red. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MessageHost(app: App, modifier: Modifier = Modifier) {
    val keyboard = WindowInsets.isImeVisible
    SnackbarHost(
        app.snackbar,
        modifier = modifier.imePadding().navigationBarsPadding()
            .padding(bottom = if (keyboard) 8.dp else 90.dp, start = 8.dp, end = 8.dp),
    ) { data ->
        val isError = data.visuals.actionLabel == ERROR
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (isError) Mx.Red else Mx.Ink)
                .padding(horizontal = 14.dp, vertical = 12.dp).testTag(if (isError) "error-message" else "message"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(if (isError) "⚠  " else "", color = Color.White, fontWeight = FontWeight.Bold)
            Text(data.visuals.message, color = Color.White, fontSize = 14.sp, modifier = Modifier.weight(1f))
            Text("OK", color = if (isError) Color.White else Mx.Gold, fontWeight = FontWeight.Bold,
                modifier = Modifier.clickable { data.dismiss() }.padding(start = 12.dp, top = 4.dp, bottom = 4.dp))
        }
    }
}

/** Blocks screenshots and screen recording while a money or PIN screen is open. */
@Composable
fun SecureScreen() {
    val activity = LocalContext.current as? Activity ?: return
    DisposableEffect(Unit) {
        activity.window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        onDispose { activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
    }
}

fun NavHostController.back() {
    if (!popBackStack()) navigate(Routes.HOME)
}
