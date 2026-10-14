package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx

@Composable
fun ProfileScreen(nav: NavHostController) {
    val app = LocalApp.current
    val me = rememberLoader(Unit) { app.api.obj("/v1/me") }
    val seller = rememberLoader(me.data) { me.data?.let { app.api.obj("/v1/sellers/${it.str("id")}") } }
    val listings = rememberLoader(Unit) { app.api.list("/v1/me/listings").objects() }
    var name by remember { mutableStateOf("") }
    var store by remember { mutableStateOf("") }
    var bio by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(me.data, seller.data) {
        me.data?.let { if (name.isEmpty()) name = it.str("display_name") }
        seller.data?.let { s -> if (bio.isEmpty()) bio = s.str("bio"); if (store.isEmpty() && s.optBoolean("is_store")) store = s.str("name") }
    }

    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("Profile", onBack = { nav.back() })
        LazyVerticalGrid(
            GridCells.Fixed(2),
            contentPadding = PaddingValues(16.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item(span = { GridItemSpan(2) }) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Field(name, { name = it }, "Your name")
                    Field(store, { store = it }, "Store name (optional)")
                    Field(bio, { bio = it.take(500) }, "About you or your store", singleLine = false, minLines = 2)
                    BigButton("Save profile", busy = busy, onClick = {
                        busy = true
                        app.launch(onDone = { busy = false }) {
                            app.api.put("/v1/me/profile", JSONObject().put("display_name", name.trim())
                                .put("store_name", store.trim().ifEmpty { null } ?: JSONObject.NULL).put("bio", bio.trim()))
                            app.displayName = name.trim()
                            app.say("Profile saved")
                        }
                    })
                    Text("My listings", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp))
                    if (listings.data?.isEmpty() == true) Text("None yet.", color = Mx.Muted)
                }
            }
            items(listings.data.orEmpty(), key = { it.str("id") }) { ListingTile(it) { nav.navigate(Routes.listing(it.str("id"))) } }
        }
    }
}
