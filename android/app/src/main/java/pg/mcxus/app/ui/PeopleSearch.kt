package pg.mcxus.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.ui.theme.Mx
import java.net.URLEncoder

/**
 * Find someone by name or number with suggestions as you type (not case-sensitive, words in any order).
 * Names from 2 letters; phone numbers when (almost) complete, so nobody can browse numbers.
 */
@Composable
fun PeopleSearch(
    query: String,
    onQuery: (String) -> Unit,
    onPick: (JSONObject) -> Unit,
    label: String = "Name or mobile number",
    tag: String = "people-search",
    modifier: Modifier = Modifier,
) {
    val app = LocalApp.current
    var results by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var answered by remember { mutableStateOf("") } // the text the current results are for
    LaunchedEffect(query) {
        val q = query.trim()
        if (q.length < 2) { results = emptyList(); answered = q; return@LaunchedEffect }
        delay(300) // wait until typing pauses
        results = runCatching { app.api.list("/v1/users/search?q=" + URLEncoder.encode(q, "UTF-8")).objects() }.getOrDefault(emptyList())
        answered = q
    }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Field(query, onQuery, label, tag = tag)
        val q = query.trim()
        // "No one found" only once the search for exactly this text has come back empty (not while typing).
        if (q.length >= 2 && results.isEmpty() && answered == q) {
            Text(
                if (q.any(Char::isDigit)) "No one found. Type the whole mobile number." else "No one found with that name.",
                color = Mx.Muted, fontSize = 13.sp, modifier = Modifier.padding(start = 4.dp),
            )
        }
        if (results.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Color.White).testTag("$tag-results")) {
                results.forEach { p ->
                    Row(
                        Modifier.fillMaxWidth().clickable { onPick(p) }.padding(horizontal = 12.dp, vertical = 8.dp).testTag("suggest-${p.str("name")}"),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Avatar(p.str("name"), 36.dp, key = p.str("id"))
                        Column(Modifier.weight(1f)) {
                            Text(p.str("name"), fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("Mobile ${p.str("phone_hint")}", fontSize = 12.sp, color = Mx.Muted)
                        }
                        SellerBadge(p.str("badge"))
                    }
                    HorizontalDivider(color = Mx.LineSoft)
                }
            }
        }
    }
}
