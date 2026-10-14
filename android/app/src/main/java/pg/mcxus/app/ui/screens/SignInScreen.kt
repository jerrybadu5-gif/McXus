package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import pg.mcxus.app.BuildConfig
import pg.mcxus.app.LocalApp
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Note
import pg.mcxus.app.ui.StarLogo
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx

/** Sign in with a PNG mobile number and a 6-digit code (in sandbox the code is shown on screen). */
@Composable
fun SignInScreen(onDone: () -> Unit) {
    val app = LocalApp.current
    var server by remember { mutableStateOf(app.session.server.ifEmpty { if (BuildConfig.DEBUG) "http://127.0.0.1:8000" else "" }) }
    var phone by remember { mutableStateOf(app.session.phone) }
    var code by remember { mutableStateOf("") }
    var codeSent by remember { mutableStateOf(false) }
    var hint by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    Column(
        Modifier.fillMaxSize().background(Mx.Bg).safeDrawingPadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Spacer(Modifier.height(24.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            StarLogo(52.dp)
            Column(Modifier.padding(start = 14.dp)) {
                Text("McXus", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold)
                Text("Chat, buy and sell safely in PNG", color = Mx.Muted, fontSize = 14.sp)
            }
        }
        Spacer(Modifier.height(8.dp))
        if (BuildConfig.DEBUG) Field(server, { server = it }, "Server address", keyboard = KeyboardType.Uri, tag = "server")
        Field(phone, { phone = it }, "Mobile number, e.g. 7000 0001", keyboard = KeyboardType.Phone, tag = "phone")
        if (codeSent) {
            Field(code, { code = it.filter(Char::isDigit).take(6) }, "6-digit code", keyboard = KeyboardType.NumberPassword, tag = "code")
            hint?.let { Note(it, icon = Ic.Lock) }
            BigButton("Sign in", busy = busy, enabled = code.length == 6, onClick = {
                busy = true
                app.launch(onDone = { busy = false }) {
                    val r = app.api.post("/v1/auth/otp/verify", JSONObject().put("phone", phone).put("code", code))
                    app.onSignedIn(r.getString("access_token"), r.getString("user_id"))
                    app.displayName = app.api.obj("/v1/me").str("display_name")
                    onDone()
                }
            })
        } else {
            BigButton("Send me a code", busy = busy, enabled = phone.isNotBlank(), onClick = {
                app.session.server = server
                app.session.phone = phone
                busy = true
                app.launch(onDone = { busy = false }) {
                    val r = app.api.post("/v1/auth/otp/request", JSONObject().put("phone", phone))
                    codeSent = true
                    hint = r.str("dev_code").let { if (it.isNotEmpty()) "Sandbox code: $it (real SMS comes later)" else "We sent a code by SMS." }
                }
            })
        }
        Note("Your personal messages are end-to-end encrypted. McXus cannot read them.", icon = Ic.Lock)
    }
}
