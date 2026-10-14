package pg.mcxus.app

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Snackbar
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
            statusBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(Color.WHITE, Color.WHITE),
        )
        super.onCreate(savedInstanceState)
        app = (application as McXusApp).app
        if (app.signedIn) app.startChat()
        pendingChat.value = intent?.getStringExtra(EXTRA_CHAT)
        setContent {
            McXusTheme {
                CompositionLocalProvider(LocalApp provides app) { Root(pendingChat) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        pendingChat.value = intent.getStringExtra(EXTRA_CHAT)
    }

    override fun onStart() {
        super.onStart()
        app.inForeground = true
    }

    override fun onStop() {
        app.inForeground = false
        super.onStop()
    }

    /** Chat to open when the person taps a notification. */
    private val pendingChat = mutableStateOf<String?>(null)

    companion object {
        const val EXTRA_CHAT = "chat"
    }
}

object Routes {
    const val SIGN_IN = "signin"
    const val HOME = "home"
    fun chat(id: String) = "chat/$id"
    fun listing(id: String) = "listing/$id"
    fun order(id: String) = "order/$id"
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
        val chat = pendingChat.value ?: return@LaunchedEffect
        if (app.signedIn) nav.navigate(Routes.chat(chat))
        pendingChat.value = null
    }
    Box(Modifier.fillMaxSize()) {
        NavHost(nav, startDestination = if (app.signedIn) Routes.HOME else Routes.SIGN_IN, modifier = Modifier.imePadding()) {
            composable(Routes.SIGN_IN) { SignInScreen(onDone = { nav.navigate(Routes.HOME) { popUpTo(0) } }) }
            composable(Routes.HOME) { HomeScreen(nav) }
            composable("chat/{id}") { ChatScreen(nav, it.arguments?.getString("id")!!) }
            composable("listing/{id}") { ListingScreen(nav, it.arguments?.getString("id")!!) }
            composable("order/{id}") { OrderScreen(nav, it.arguments?.getString("id")!!) }
            composable(Routes.NEW_CHAT) { NewChatScreen(nav) }
            composable(Routes.NEW_GROUP) { NewGroupScreen(nav) }
            composable("group/{id}") { GroupInfoScreen(nav, it.arguments?.getString("id")!!) }
            composable(Routes.SELL) { SellScreen(nav) }
            composable(Routes.ORDERS) { OrdersScreen(nav) }
            composable(Routes.PROFILE) { ProfileScreen(nav) }
        }
        SnackbarHost(
            app.snackbar,
            modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = 90.dp),
        ) { Snackbar(it, containerColor = Mx.Ink) }
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
