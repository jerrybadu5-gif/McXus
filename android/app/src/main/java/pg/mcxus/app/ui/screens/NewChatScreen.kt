package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
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
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Card
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Note
import pg.mcxus.app.ui.SellerBadge
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx

/** Find someone by mobile number and start an encrypted chat. */
@Composable
fun NewChatScreen(nav: NavHostController) {
    val app = LocalApp.current
    var phone by remember { mutableStateOf("") }
    var found by remember { mutableStateOf<JSONObject?>(null) }
    var busy by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("New chat", onBack = { nav.back() })
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Field(phone, { phone = it; found = null }, "Their mobile number", keyboard = KeyboardType.Phone, tag = "lookup-phone")
            val person = found
            if (person == null) {
                BigButton("Find", busy = busy, enabled = phone.isNotBlank(), onClick = {
                    busy = true
                    app.launch(onDone = { busy = false }) {
                        found = app.api.post("/v1/users/lookup", JSONObject().put("phone", phone))
                    }
                })
            } else {
                Card {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Avatar(person.str("name"), 48.dp, key = person.str("id"))
                        Column(Modifier.weight(1f)) {
                            Text(person.str("name"), fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            val rating = person.str("rating")
                            Text(if (rating.isNotEmpty()) "★ $rating · ${person.optInt("reviews")} reviews" else "On McXus",
                                color = Mx.Muted, fontSize = 13.sp)
                        }
                        SellerBadge(person.str("badge"))
                    }
                }
                BigButton("Start encrypted chat", busy = busy, onClick = {
                    val engine = app.chat ?: return@BigButton app.say("Encryption is still starting, try again in a second.", error = true)
                    busy = true
                    app.launch(onDone = { busy = false }) {
                        val id = engine.open(person.str("id"))
                        nav.navigate(Routes.chat(id)) { popUpTo(Routes.HOME) }
                    }
                })
            }
            Note("Only you and the person you message can read what you send. Never share your handover PIN or pay outside McXus.", icon = Ic.Lock)
        }
    }
}
