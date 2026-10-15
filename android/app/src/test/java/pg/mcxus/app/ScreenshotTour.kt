package pg.mcxus.app

import android.graphics.Bitmap
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.navigation.compose.rememberNavController
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import pg.mcxus.app.chat.ChatEngine
import pg.mcxus.app.chat.Payload
import pg.mcxus.app.net.Api
import pg.mcxus.app.net.Session
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.screens.ChatScreen
import pg.mcxus.app.ui.screens.HomeScreen
import pg.mcxus.app.ui.screens.ListingScreen
import pg.mcxus.app.ui.screens.OrderScreen
import pg.mcxus.app.ui.screens.SellScreen
import pg.mcxus.app.ui.screens.SignInScreen
import pg.mcxus.app.ui.theme.McXusTheme
import java.io.File
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import kotlin.random.Random

/**
 * Renders every main screen against a running server with real data and saves PNGs (design review without a
 * phone). Runs only with MCXUS_E2E_SERVER, MCXUS_SCREENSHOTS=<folder> and MCXUS_ADMIN_TOKEN (python -m app.cli dev-token).
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w390dp-h844dp-xhdpi")
class ScreenshotTour {
    @get:Rule val compose = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    private val server = System.getenv("MCXUS_E2E_SERVER")
    private val out = System.getenv("MCXUS_SCREENSHOTS")
    private val adminToken = System.getenv("MCXUS_ADMIN_TOKEN")

    private fun signUp(session: Session, name: String): String = runBlocking {
        session.server = server!!
        val api = Api(session)
        val number = "7" + Random.nextInt(1_000_000, 9_999_999)
        session.phone = number
        val code = api.post("/v1/auth/otp/request", JSONObject().put("phone", number)).getString("dev_code")
        val t = api.post("/v1/auth/otp/verify", JSONObject().put("phone", number).put("code", code))
        session.token = t.getString("access_token")
        session.userId = t.getString("user_id")
        api.put("/v1/me/profile", JSONObject().put("display_name", name).put("bio", ""))
        // Verify the test account (level 2) with a staff token so it can sell and hold Stars.
        val admin = Session(ApplicationProvider.getApplicationContext(), "tour-admin").apply { this.server = this@ScreenshotTour.server!!; token = adminToken }
        Api(admin).post("/v1/admin/users/${t.getString("user_id")}/kyc-tier", JSONObject().put("kyc_tier", 2))
        t.getString("user_id")
    }

    @Test
    fun tour() {
        assumeTrue(!server.isNullOrBlank() && !out.isNullOrBlank() && !adminToken.isNullOrBlank())
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()

        // Seller with two listings
        val sellerSession = Session(context, "tour-seller")
        val sellerId = signUp(sellerSession, "Kila Solar Supplies")
        val sellerApi = Api(sellerSession)
        val listingId = runBlocking {
            val cat = sellerApi.list("/v1/categories").objects().first().getJSONArray("children").getJSONObject(0).getInt("id")
            val province = sellerApi.list("/v1/locations").objects().first { it.getString("name").contains("Morobe") }.getInt("id")
            sellerApi.post("/v1/listings", JSONObject().put("title", "Bilum, hand-woven, large").put("price", "85.00").put("category_id", cat)
                .put("province_id", province).put("condition", "new").put("description", "Made in Goroka. Strong strap, bright colours."))
            sellerApi.post("/v1/listings", JSONObject().put("title", "Solar lamp with phone charger").put("price", "120.00").put("quantity", 2)
                .put("category_id", cat).put("province_id", province).put("condition", "new")
                .put("delivery_options", org.json.JSONArray(listOf("meetup", "pickup", "courier")))
                .put("latitude", "-6.72900").put("longitude", "146.99700").put("meetup_address", "Eriku market gate, near BSP ATM")
                .put("description", "Two bright bulbs and a 10 W panel. Charges two phones at once. Pickup at Eriku market gate after 3 pm."))
                .getString("id")
        }

        // Buyer = the app's own session
        val app = App(context, MainScope())
        signUp(app.session, "Jerry Badu")
        app.displayName = "Jerry Badu"
        app.onSignedIn(app.session.token!!, app.session.userId!!)
        val deadline = System.currentTimeMillis() + 30_000
        while (app.chat == null && System.currentTimeMillis() < deadline) {
            org.robolectric.Shadows.shadowOf(android.os.Looper.getMainLooper()).idle() // App starts chat on the main thread
            Thread.sleep(50)
        }
        val seller = runBlocking { ChatEngine.create(context, sellerApi, sellerId).also { it.start() } }
        val (conv, orderId) = runBlocking {
            app.api.post("/v1/wallet/sandbox-topup", JSONObject().put("amount", "500.00"), idempotent = true)
            withTimeout(30_000) { while (app.chat?.online?.value != true || !seller.online.value) delay(100) }
            val buyer = app.chat!!
            val conv = buyer.open(sellerId, listingId)
            buyer.send(conv, Payload.text("Moning! Is the solar lamp still available?"))
            buyer.send(conv, Payload.listing(listingId, "Solar lamp with phone charger", "120.00", ""))
            withTimeout(30_000) { while (seller.messages(conv).isEmpty()) delay(100) }
            seller.send(conv, Payload.text("Yes, the lamp is still available. K120 with phone charger."))
            val order = app.api.post("/v1/listings/$listingId/buy", JSONObject().put("quantity", 1)
                .put("delivery", JSONObject().put("method", "meetup")), idempotent = true)
            val orderId = order.getString("id")
            app.session.pins[orderId] = app.api.post("/v1/orders/$orderId/pay", idempotent = true).getString("handover_pin")
            buyer.send(conv, Payload.order(orderId, "Solar lamp with phone charger", "120.00"))
            buyer.send(conv, Payload.text("Can I collect at Eriku after 3pm?"))
            seller.send(conv, Payload.location(pg.mcxus.app.util.Place.of(-6.729, 146.997, "Eriku market gate, near BSP ATM")))
            withTimeout(30_000) { while (buyer.messages(conv).none { it.payload.contains("location") }) delay(100) }
            withTimeout(30_000) { while (buyer.messages(conv).none { !it.mine }) delay(100) }
            conv to orderId
        }
        // A group with the seller and a third person, with a photo and a voice note.
        val ruthSession = Session(context, "tour-ruth")
        val ruthId = signUp(ruthSession, "Mama Ruth")
        val ruth = runBlocking { ChatEngine.create(context, Api(ruthSession), ruthId).also { it.start() } }
        val group = runBlocking {
            withTimeout(30_000) { while (!ruth.online.value) delay(100) }
            val buyer = app.chat!!
            val (g, _) = buyer.createGroup("Eriku Youth Group", listOf(sellerId, ruthId))
            withTimeout(30_000) {
                while (seller.ensureReady(g) != pg.mcxus.app.chat.Readiness.Ready || ruth.ensureReady(g) != pg.mcxus.app.chat.Readiness.Ready) delay(200)
            }
            seller.send(g, Payload.text("Moning olgeta! Youth meeting Saturday 3pm at the church hall."))
            val bmp = android.graphics.Bitmap.createBitmap(640, 480, android.graphics.Bitmap.Config.ARGB_8888)
            android.graphics.Canvas(bmp).apply {
                drawColor(0xFF134074.toInt())
                drawCircle(320f, 240f, 150f, android.graphics.Paint().apply { color = 0xFFE9A23B.toInt() })
            }
            val jpeg = java.io.ByteArrayOutputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, it); it.toByteArray() }
            ruth.sendImage(g, jpeg, 640, 480, pg.mcxus.app.util.Images.thumbnail(jpeg), "Poster for Saturday")
            ruth.sendVoice(g, ByteArray(20_000) { 1 }, 12_400)
            buyer.send(g, Payload.text("Tenkyu Mama Ruth, I will bring the speakers."))
            withTimeout(30_000) { while (buyer.messages(g).none { it.payload.contains("voice") }) delay(100) }
            g
        }

        var screen by mutableStateOf("signin")
        compose.setContent {
            McXusTheme {
                CompositionLocalProvider(LocalApp provides app) {
                    androidx.compose.foundation.layout.Box(androidx.compose.ui.Modifier.fillMaxSize()) {
                        Screen(screen, conv, listingId, orderId, group)
                        MessageHost(app, androidx.compose.ui.Modifier.align(androidx.compose.ui.Alignment.BottomCenter))
                    }
                }
            }
        }
        val dir = File(out!!).apply { mkdirs() }
        listOf("signin", "chats", "chat", "discover", "market", "listing", "sell", "wallet", "order", "me", "place", "map", "group-chat", "group-info", "new-group", "sell-error", "error-toast", "dispute", "order-disputed", "dispute-decided").forEachIndexed { i, name ->
            if (name == "dispute") app.snackbar.currentSnackbarData?.dismiss()
            if (name == "dispute") runBlocking {
                // The seller accepts, the buyer disputes with a photo, the seller offers K40 back.
                sellerApi.post("/v1/orders/$orderId/accept")
                app.api.post("/v1/orders/$orderId/dispute", JSONObject().put("reason", "The panel is cracked and the lamp does not charge."))
                val bmp = android.graphics.Bitmap.createBitmap(800, 600, android.graphics.Bitmap.Config.ARGB_8888)
                android.graphics.Canvas(bmp).apply {
                    drawColor(0xFF263445.toInt())
                    drawLine(120f, 80f, 680f, 520f, android.graphics.Paint().apply { color = 0xFFE9EEF4.toInt(); strokeWidth = 10f })
                }
                val jpeg = java.io.ByteArrayOutputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 85, it); it.toByteArray() }
                app.api.upload("/v1/disputes/$orderId/photos", jpeg)
                sellerApi.post("/v1/disputes/$orderId/offers", JSONObject().put("buyer_refund", "40.00").put("note", "Sorry! K40 back for the panel?"))
            }
            if (name == "dispute-decided") runBlocking {
                app.api.post("/v1/disputes/$orderId/escalate")
                val admin = Session(context, "tour-admin").apply { this.server = this@ScreenshotTour.server!!; token = adminToken }
                Api(admin).post("/v1/admin/disputes/$orderId/decide",
                    JSONObject().put("buyer_refund", "60.00").put("note", "The photo shows a cracked panel; half back."))
            }
            screen = when (name) {
                "sell-error" -> "sell"
                "error-toast" -> "market"
                "dispute-decided" -> "dispute"
                "order-disputed" -> "order"
                else -> name
            }
            compose.waitForIdle()
            if (name == "sell-error") {
                Thread.sleep(1500)
                compose.onNodeWithTag("post-listing", useUnmergedTree = true).performClick()
            }
            if (name == "error-toast") app.say(pg.mcxus.app.OUTDATED, error = true)
            Thread.sleep(2500) // let network loads finish
            compose.waitForIdle()
            val view = compose.activity.window.decorView
            val bmp = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(android.graphics.Canvas(bmp))
            File(dir, "%02d-%s.png".format(i + 1, name)).outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        seller.stop()
        ruth.stop()
        app.chat?.stop()
    }

    @Composable
    private fun Screen(name: String, conv: String, listingId: String, orderId: String, group: String) {
        val nav = rememberNavController()
        when (name) {
            "signin" -> SignInScreen(onDone = {})
            "chats" -> HomeScreen(nav, initialTab = 0)
            "discover" -> HomeScreen(nav, initialTab = 1)
            "market" -> HomeScreen(nav, initialTab = 2)
            "wallet" -> HomeScreen(nav, initialTab = 3)
            "me" -> HomeScreen(nav, initialTab = 4)
            "chat" -> ChatScreen(nav, conv)
            "listing" -> ListingScreen(nav, listingId)
            "sell" -> SellScreen(nav)
            "order" -> OrderScreen(nav, orderId)
            "dispute" -> pg.mcxus.app.ui.screens.DisputeScreen(nav, orderId)
            "place" -> androidx.compose.foundation.layout.Box(androidx.compose.ui.Modifier.padding(16.dp)) {
                pg.mcxus.app.ui.PlaceField("Meet-up / pickup point", pg.mcxus.app.util.Place.of(-6.729, 146.997, "Eriku market gate"), {})
            }
            "group-chat" -> ChatScreen(nav, group)
            "group-info" -> pg.mcxus.app.ui.screens.GroupInfoScreen(nav, group)
            "new-group" -> pg.mcxus.app.ui.screens.NewGroupScreen(nav)
            "map" -> pg.mcxus.app.ui.MapPicker(pg.mcxus.app.util.Place.of(-6.729, 146.997), {}, { _, _ -> })
        }
    }
}
