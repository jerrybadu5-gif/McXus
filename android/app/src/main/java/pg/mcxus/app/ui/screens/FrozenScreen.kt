package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Card
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format

/**
 * Shown instead of the app while the account is frozen: why, when, and one appeal. Staff decide in the console
 * (someone other than the person who froze it); the decision and its reason appear here.
 */
@Composable
fun FrozenScreen() {
    val app = LocalApp.current
    var refresh by remember { mutableIntStateOf(0) }
    val loader = rememberLoader(refresh) { app.api.get("/v1/me/freeze").let { if (it.trim() == "null") null else JSONObject(it) } }
    var appeal by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }

    Column(
        Modifier.fillMaxSize().background(Mx.Navy).statusBarsPadding().navigationBarsPadding()
            .verticalScroll(rememberScrollState()).padding(20.dp).testTag("frozen-screen"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Icon(Ic.Lock, null, tint = Mx.Gold, modifier = Modifier.size(40.dp))
        Text("Your account is frozen", color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 24.sp)
        Text("You can't use chats, the market or your wallet until it is unfrozen. Your Stars are safe and stay in your wallet.",
            color = Mx.OnNavyMuted, fontSize = 14.sp, lineHeight = 20.sp)
        val case = loader.data
        if (case == null) {
            if (loader.loading) Loading() else Card { Text("Contact McXus support to find out why.", fontSize = 14.sp) }
        } else {
            Card {
                Text("Why", fontSize = 12.sp, color = Mx.Muted)
                Text(case.str("reason"), fontSize = 15.sp, color = Mx.Ink, fontWeight = FontWeight.SemiBold)
                Text("Frozen ${Format.dateTime(case.str("frozen_at"))}", fontSize = 12.sp, color = Mx.Muted)
            }
            when (case.str("status")) {
                "frozen" -> Card {
                    Text("Appeal", fontWeight = FontWeight.Bold, color = Mx.Ink)
                    Text("Explain why the account should be unfrozen. You can appeal once; a different staff member reviews it.",
                        fontSize = 13.sp, color = Mx.Body)
                    Spacer(Modifier.height(8.dp))
                    Field(appeal, { appeal = it.take(2000) }, "Your appeal", singleLine = false, minLines = 4, tag = "appeal-text")
                    Spacer(Modifier.height(8.dp))
                    BigButton("Send appeal", busy = busy, enabled = appeal.trim().length >= 10, onClick = {
                        busy = true
                        app.launch(onDone = { busy = false }) {
                            app.api.post("/v1/me/freeze/appeal", JSONObject().put("text", appeal.trim()))
                            app.say("Appeal sent. You'll see the answer here.")
                            refresh++
                        }
                    })
                }
                "appealed" -> Card {
                    Text("Your appeal is being reviewed", fontWeight = FontWeight.Bold, color = Mx.Ink)
                    Text("Sent ${Format.dateTime(case.str("appealed_at"))}", fontSize = 12.sp, color = Mx.Muted)
                    Text(case.str("appeal_text"), fontSize = 14.sp, color = Mx.Body)
                }
                "upheld" -> Card {
                    Text("Your appeal was refused", fontWeight = FontWeight.Bold, color = Mx.Red)
                    Text(case.str("decision_note"), fontSize = 14.sp, color = Mx.Ink)
                    Text("Contact McXus support if you have new information.", fontSize = 12.sp, color = Mx.Muted)
                }
            }
        }
        LineButton("Check again", {
            app.launch { app.refreshStatus(); refresh++ }
        }, Modifier.fillMaxWidth(), color = Color.White)
        LineButton("Sign out", { app.signOut() }, Modifier.fillMaxWidth(), color = Mx.Gold)
    }
}
