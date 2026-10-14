package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.SecureScreen
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.Tag
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format

@Composable
fun WalletTab(nav: NavHostController) {
    SecureScreen()
    val app = LocalApp.current
    var refresh by remember { mutableIntStateOf(0) }
    val wallet = rememberLoader(refresh) { app.api.obj("/v1/wallet") }
    val statement = rememberLoader(refresh) { app.api.list("/v1/wallet/statement?limit=50").objects() }
    var hidden by rememberSaveable { mutableStateOf(false) }
    var dialog by remember { mutableStateOf<String?>(null) }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Row(Modifier.statusBarsPadding().padding(top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Wallet", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
                if (wallet.data?.optBoolean("sandbox", true) != false) Tag("SANDBOX · test Stars")
                IconButton(onClick = { refresh++ }) { Icon(Ic.Refresh, "Refresh", tint = Mx.Blue) }
            }
        }
        item {
            val w = wallet.data
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(Mx.Navy).padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Ic.Star, null, tint = Mx.Gold, modifier = Modifier.size(26.dp))
                    Text("  Available Stars", color = Mx.OnNavyMuted, fontSize = 14.sp, modifier = Modifier.weight(1f))
                    IconButton(onClick = { hidden = !hidden }) { Icon(Ic.Eye, if (hidden) "Show balance" else "Hide balance", tint = Mx.OnNavyMuted) }
                }
                Text(
                    when {
                        w == null -> wallet.error ?: "…"
                        hidden -> "K •••••"
                        else -> Format.kina(w.str("balance"))
                    },
                    color = Color.White, fontSize = if (w == null && wallet.error != null) 14.sp else 38.sp, fontWeight = FontWeight.ExtraBold,
                    modifier = Modifier.testTag("balance"),
                )
                if (w != null) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        MiniStat("Owed in fees", Format.kina(w.str("penalties_owed")), Modifier.weight(1f))
                        val limit = w.str("monthly_in_limit")
                        MiniStat("This month in", Format.kina(w.str("monthly_in_used")), Modifier.weight(1f),
                            if (limit.isNotEmpty()) "limit ${Format.kina(limit)}" else "")
                    }
                    Text("Level ${w.optInt("kyc_tier")} · ${w.str("kyc_tier_name")}", color = Mx.OnNavyMuted, fontSize = 12.sp)
                }
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Action("Top up", Ic.Up, Modifier.weight(1f)) { dialog = "topup" }
                Action("Withdraw", Ic.Out, Modifier.weight(1f)) { dialog = "withdraw" }
                Action("Orders", Ic.Receipt, Modifier.weight(1f)) { nav.navigate(Routes.ORDERS) }
                Action("Send", Ic.Swap, Modifier.weight(1f)) { app.say("Send Stars to a friend comes after sandbox testing.") }
            }
        }
        item {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Color.White).padding(14.dp)) {
                Text("Services · coming next", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                Row(Modifier.padding(top = 10.dp)) {
                    listOf("AT" to "Airtime", "PW" to "Power", "SF" to "School fees", "BL" to "Bills").forEach { (s, l) ->
                        Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                            Box(Modifier.size(38.dp).clip(CircleShape).background(Mx.GoldSoft), contentAlignment = Alignment.Center) {
                                Text(s, color = Mx.GoldInk, fontWeight = FontWeight.ExtraBold, fontSize = 12.sp)
                            }
                            Text(l, fontSize = 11.sp, color = Mx.Body, modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }
        }
        item { Text("Recent activity", fontWeight = FontWeight.Bold) }
        val lines = statement.data
        if (lines == null) {
            item { if (statement.error != null) Text(statement.error!!, color = Mx.Muted) else Loading() }
        } else if (lines.isEmpty()) {
            item { Text("No activity yet. Tap Top up to add sandbox Stars.", color = Mx.Muted, fontSize = 14.sp) }
        } else {
            items(lines) { l ->
                val amount = l.str("amount")
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Color.White).padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(l.str("description"), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(Format.dateTime(l.str("at")), fontSize = 12.sp, color = Mx.Muted)
                    }
                    Text(
                        if (hidden) "•••" else (if (amount.startsWith("-")) "" else "+") + Format.kina(amount),
                        color = if (amount.startsWith("-")) Mx.Ink else Mx.Green, fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }

    when (dialog) {
        "topup" -> AmountDialog("Add sandbox Stars", "Test Stars only — no real money moves.", withBank = false, onDismiss = { dialog = null }) { amount, _ ->
            app.launch {
                app.api.post("/v1/wallet/sandbox-topup", JSONObject().put("amount", amount), idempotent = true)
                app.say("Added ${Format.kina(amount)}")
                refresh++
            }
        }
        "withdraw" -> AmountDialog("Withdraw to bank", "Finance staff send it to your bank account. A fee may apply.", withBank = true, onDismiss = { dialog = null }) { amount, bank ->
            app.launch {
                app.api.post("/v1/wallet/withdrawals", JSONObject().put("amount", amount).put("bank_account", bank), idempotent = true)
                app.say("Withdrawal requested")
                refresh++
            }
        }
    }
}

@Composable
private fun MiniStat(label: String, value: String, modifier: Modifier, note: String = "") {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(Mx.NavySoft).padding(10.dp)) {
        Text(label, color = Mx.OnNavyMuted, fontSize = 12.sp)
        Text(value, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1)
        if (note.isNotEmpty()) Text(note, color = Mx.OnNavyMuted, fontSize = 11.sp, maxLines = 1)
    }
}

@Composable
private fun Action(label: String, icon: ImageVector, modifier: Modifier, onClick: () -> Unit) {
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(Color.White).clickable(onClick = onClick).padding(vertical = 12.dp).testTag("wallet-$label"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(Mx.Tint), contentAlignment = Alignment.Center) {
            Icon(icon, null, tint = Mx.Blue, modifier = Modifier.size(22.dp))
        }
        Text(label, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
    }
}

@Composable
private fun AmountDialog(title: String, note: String, withBank: Boolean, onDismiss: () -> Unit, onOk: (String, String) -> Unit) {
    val app = LocalApp.current
    var amount by remember { mutableStateOf("") }
    var bank by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(note, fontSize = 13.sp, color = Mx.Muted)
                Field(amount, { amount = it }, "Amount in Kina, e.g. 200", keyboard = KeyboardType.Decimal, tag = "amount")
                if (withBank) Field(bank, { bank = it }, "Bank and account, e.g. BSP 1001234567 J Badu")
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val value = Format.amount(amount)
                if (value == null) app.say("Enter an amount like 200 or 12.50")
                else if (withBank && bank.trim().length < 4) app.say("Enter your bank and account number")
                else { onDismiss(); onOk(value, bank.trim()) }
            }, modifier = Modifier.testTag("amount-ok")) { Text("OK") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
