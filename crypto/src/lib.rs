//! McXus end-to-end encryption (ADR 0008).
//!
//! A thin wrapper over OpenMLS (RFC 9420, MIT licence). We never implement cryptography ourselves: this
//! file only wires OpenMLS calls together, saves the MLS state to a file in the app's private storage,
//! and exposes six functions to Kotlin through uniffi.
//!
//! One-to-one chat: A claims one of B's KeyPackages from the server, creates a two-member MLS group whose
//! group id is the conversation id, and uploads the Welcome. B joins from the Welcome. After that every
//! message is an MLS application message (forward secrecy and post-compromise security come from MLS).
//!
//! Groups (M3.2, up to 256 people): an admin creates the group alone, then adds people with a Commit (sent to
//! existing members) and a Welcome (for the new ones). The server accepts only one Commit per epoch, so every
//! phone applies the same changes in the same order; a phone whose Commit was refused discards it and retries.

use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use openmls::prelude::tls_codec::{Deserialize as _, Serialize as _};
use openmls::prelude::*;
use openmls_basic_credential::SignatureKeyPair;
use openmls_memory_storage::MemoryStorage;
use openmls_rust_crypto::RustCrypto;
use openmls_traits::types::SignatureScheme;
use openmls_traits::OpenMlsProvider;
use sha2::{Digest, Sha256};

uniffi::setup_scaffolding!();

const CIPHERSUITE: Ciphersuite = Ciphersuite::MLS_128_DHKEMX25519_AES128GCM_SHA256_Ed25519;
const FILE_MAGIC: &[u8; 6] = b"MCXS01";
/// Keep message keys for 3 earlier epochs so a message sent just before a membership change still decrypts.
/// Kept small on purpose: older keys weaken forward secrecy.
const MAX_PAST_EPOCHS: usize = 3;

#[derive(Debug, thiserror::Error, uniffi::Error)]
pub enum CryptoError {
    #[error("{reason}")]
    Failed { reason: String },
}

fn fail<E: std::fmt::Debug>(context: &'static str) -> impl Fn(E) -> CryptoError {
    move |e| CryptoError::Failed { reason: format!("{context}: {e:?}") }
}

/// A decrypted incoming message.
#[derive(uniffi::Record)]
pub struct Decrypted {
    /// "application" (plaintext is set), "commit" (group changed) or "other".
    pub kind: String,
    pub plaintext: Option<Vec<u8>>,
    /// The sender's MLS identity (for McXus: "user:<uuid>").
    pub sender: String,
}

/// A membership change created on this phone, waiting for the server to accept it.
#[derive(uniffi::Record)]
pub struct GroupChange {
    /// Send to the current members (via the server, with `epoch`).
    pub commit: Vec<u8>,
    /// Send to the new members (only when people were added).
    pub welcome: Option<Vec<u8>>,
    /// The epoch the commit was made in; the server accepts it only if this is still the group's epoch.
    pub epoch: u64,
}

#[derive(Default)]
struct Provider {
    crypto: RustCrypto,
    storage: MemoryStorage,
}

impl OpenMlsProvider for Provider {
    type CryptoProvider = RustCrypto;
    type RandProvider = RustCrypto;
    type StorageProvider = MemoryStorage;

    fn storage(&self) -> &Self::StorageProvider {
        &self.storage
    }
    fn crypto(&self) -> &Self::CryptoProvider {
        &self.crypto
    }
    fn rand(&self) -> &Self::RandProvider {
        &self.crypto
    }
}

struct Inner {
    provider: Provider,
    signer: SignatureKeyPair,
    credential: CredentialWithKey,
    identity: String,
    path: PathBuf,
}

/// One device's MLS client. Thread-safe; every call that changes state saves it before returning.
#[derive(uniffi::Object)]
pub struct MlsClient {
    inner: Mutex<Inner>,
}

#[uniffi::export]
impl MlsClient {
    /// Open (or create) the client whose state lives at `state_path`. `identity` must stay the same for
    /// that file (use one file per signed-in user).
    #[uniffi::constructor]
    pub fn open(state_path: String, identity: String) -> Result<Arc<Self>, CryptoError> {
        let path = PathBuf::from(state_path);
        let provider = Provider::default();
        let mut stored_public: Option<Vec<u8>> = None;
        if path.exists() {
            let (stored_identity, public, values) = read_state(&path)?;
            if stored_identity != identity {
                return Err(CryptoError::Failed { reason: "state file belongs to another identity".into() });
            }
            *provider.storage.values.write().map_err(fail("storage lock"))? = values;
            stored_public = Some(public);
        }
        let signer = match stored_public {
            Some(public) => SignatureKeyPair::read(provider.storage(), &public, SignatureScheme::ED25519)
                .ok_or_else(|| CryptoError::Failed { reason: "signature key missing from state".into() })?,
            None => {
                let signer = SignatureKeyPair::new(SignatureScheme::ED25519).map_err(fail("new signature key"))?;
                signer.store(provider.storage()).map_err(fail("store signature key"))?;
                signer
            }
        };
        let credential = CredentialWithKey {
            credential: BasicCredential::new(identity.clone().into_bytes()).into(),
            signature_key: signer.to_public_vec().into(),
        };
        let inner = Inner { provider, signer, credential, identity, path };
        inner.save()?;
        Ok(Arc::new(Self { inner: Mutex::new(inner) }))
    }

    pub fn identity(&self) -> String {
        self.lock().identity.clone()
    }

    /// `count` fresh one-time KeyPackages (TLS-encoded) to upload to the server.
    pub fn key_packages(&self, count: u32) -> Result<Vec<Vec<u8>>, CryptoError> {
        let inner = self.lock();
        let mut out = Vec::with_capacity(count as usize);
        for _ in 0..count {
            let bundle = KeyPackage::builder()
                .build(CIPHERSUITE, &inner.provider, &inner.signer, inner.credential.clone())
                .map_err(fail("build key package"))?;
            out.push(bundle.key_package().tls_serialize_detached().map_err(fail("encode key package"))?);
        }
        inner.save()?;
        Ok(out)
    }

    /// Start a two-person encrypted chat: create group `group_id` with the peer's KeyPackage.
    /// Returns the Welcome to upload for the peer.
    pub fn create_direct(&self, group_id: Vec<u8>, peer_key_package: Vec<u8>) -> Result<Vec<u8>, CryptoError> {
        let inner = self.lock();
        let key_package = KeyPackageIn::tls_deserialize_exact(peer_key_package.as_slice())
            .map_err(fail("decode key package"))?
            .validate(inner.provider.crypto(), ProtocolVersion::Mls10)
            .map_err(fail("invalid key package"))?;
        let config = create_config();
        let mut group = MlsGroup::new_with_group_id(
            &inner.provider,
            &inner.signer,
            &config,
            GroupId::from_slice(&group_id),
            inner.credential.clone(),
        )
        .map_err(fail("create group"))?;
        let (_commit, welcome, _info) = group
            .add_members(&inner.provider, &inner.signer, core::slice::from_ref(&key_package))
            .map_err(fail("add member"))?;
        group.merge_pending_commit(&inner.provider).map_err(fail("merge commit"))?;
        let bytes = welcome.to_bytes().map_err(fail("encode welcome"))?;
        inner.save()?;
        Ok(bytes)
    }

    /// Join a chat from a Welcome. Returns the group id (the conversation id).
    pub fn join(&self, welcome: Vec<u8>) -> Result<Vec<u8>, CryptoError> {
        let inner = self.lock();
        let message = MlsMessageIn::tls_deserialize_exact(welcome.as_slice()).map_err(fail("decode welcome"))?;
        let welcome = match message.extract() {
            MlsMessageBodyIn::Welcome(welcome) => welcome,
            _ => return Err(CryptoError::Failed { reason: "not a Welcome message".into() }),
        };
        let config = MlsGroupJoinConfig::builder()
            .use_ratchet_tree_extension(true)
            .max_past_epochs(MAX_PAST_EPOCHS)
            .build();
        let group = StagedWelcome::new_from_welcome(&inner.provider, &config, welcome, None)
            .map_err(fail("stage welcome"))?
            .into_group(&inner.provider)
            .map_err(fail("join group"))?;
        let id = group.group_id().as_slice().to_vec();
        inner.save()?;
        Ok(id)
    }

    pub fn has_group(&self, group_id: Vec<u8>) -> bool {
        let inner = self.lock();
        matches!(MlsGroup::load(inner.provider.storage(), &GroupId::from_slice(&group_id)), Ok(Some(_)))
    }

    pub fn encrypt(&self, group_id: Vec<u8>, plaintext: Vec<u8>) -> Result<Vec<u8>, CryptoError> {
        let inner = self.lock();
        let mut group = inner.load_group(&group_id)?;
        let message = group
            .create_message(&inner.provider, &inner.signer, &plaintext)
            .map_err(fail("encrypt"))?;
        let bytes = message.to_bytes().map_err(fail("encode message"))?;
        inner.save()?;
        Ok(bytes)
    }

    pub fn decrypt(&self, group_id: Vec<u8>, message: Vec<u8>) -> Result<Decrypted, CryptoError> {
        let inner = self.lock();
        let mut group = inner.load_group(&group_id)?;
        let protocol: ProtocolMessage = MlsMessageIn::tls_deserialize_exact(message.as_slice())
            .map_err(fail("decode message"))?
            .try_into_protocol_message()
            .map_err(fail("not a group message"))?;
        if protocol.content_type() == ContentType::Commit && protocol.epoch() < group.epoch() {
            // A change made before this phone joined (or already applied): nothing to do.
            return Ok(Decrypted { kind: "old".into(), plaintext: None, sender: String::new() });
        }
        let processed = group.process_message(&inner.provider, protocol).map_err(fail("decrypt"))?;
        let sender = String::from_utf8_lossy(processed.credential().serialized_content()).into_owned();
        let result = match processed.into_content() {
            ProcessedMessageContent::ApplicationMessage(app) => {
                Decrypted { kind: "application".into(), plaintext: Some(app.into_bytes()), sender }
            }
            ProcessedMessageContent::StagedCommitMessage(staged) => {
                group.merge_staged_commit(&inner.provider, *staged).map_err(fail("merge commit"))?;
                // "removed": this phone was taken out of the group and can no longer read it.
                let kind = if group.is_active() { "commit" } else { "removed" };
                Decrypted { kind: kind.into(), plaintext: None, sender }
            }
            _ => Decrypted { kind: "other".into(), plaintext: None, sender },
        };
        inner.save()?;
        Ok(result)
    }

    /// Create a group with only this phone in it (then add people with `add_members`).
    pub fn create_group(&self, group_id: Vec<u8>) -> Result<(), CryptoError> {
        let inner = self.lock();
        MlsGroup::new_with_group_id(
            &inner.provider,
            &inner.signer,
            &create_config(),
            GroupId::from_slice(&group_id),
            inner.credential.clone(),
        )
        .map_err(fail("create group"))?;
        inner.save()
    }

    /// Add people (one claimed KeyPackage each). The change stays pending until `confirm_change` (server
    /// accepted) or `discard_change` (server refused because someone else changed the group first).
    pub fn add_members(&self, group_id: Vec<u8>, key_packages: Vec<Vec<u8>>) -> Result<GroupChange, CryptoError> {
        let inner = self.lock();
        let mut group = inner.load_group(&group_id)?;
        let mut packages = Vec::with_capacity(key_packages.len());
        for bytes in key_packages {
            packages.push(
                KeyPackageIn::tls_deserialize_exact(bytes.as_slice())
                    .map_err(fail("decode key package"))?
                    .validate(inner.provider.crypto(), ProtocolVersion::Mls10)
                    .map_err(fail("invalid key package"))?,
            );
        }
        let epoch = group.epoch().as_u64();
        let (commit, welcome, _info) =
            group.add_members(&inner.provider, &inner.signer, &packages).map_err(fail("add members"))?;
        let change = GroupChange {
            commit: commit.to_bytes().map_err(fail("encode commit"))?,
            welcome: Some(welcome.to_bytes().map_err(fail("encode welcome"))?),
            epoch,
        };
        inner.save()?;
        Ok(change)
    }

    /// Remove people by identity ("user:<uuid>"). Unknown identities are ignored. Pending like `add_members`.
    pub fn remove_members(&self, group_id: Vec<u8>, identities: Vec<String>) -> Result<GroupChange, CryptoError> {
        let inner = self.lock();
        let mut group = inner.load_group(&group_id)?;
        let leaves: Vec<LeafNodeIndex> = group
            .members()
            .filter(|m| identities.iter().any(|id| id.as_bytes() == m.credential.serialized_content()))
            .map(|m| m.index)
            .collect();
        if leaves.is_empty() {
            return Err(CryptoError::Failed { reason: "none of those people are in the group".into() });
        }
        let epoch = group.epoch().as_u64();
        let (commit, _welcome, _info) =
            group.remove_members(&inner.provider, &inner.signer, &leaves).map_err(fail("remove members"))?;
        let change = GroupChange { commit: commit.to_bytes().map_err(fail("encode commit"))?, welcome: None, epoch };
        inner.save()?;
        Ok(change)
    }

    /// The server accepted this phone's pending change: apply it.
    pub fn confirm_change(&self, group_id: Vec<u8>) -> Result<(), CryptoError> {
        let inner = self.lock();
        let mut group = inner.load_group(&group_id)?;
        group.merge_pending_commit(&inner.provider).map_err(fail("merge commit"))?;
        inner.save()
    }

    /// The server refused this phone's pending change (another change came first): drop it.
    pub fn discard_change(&self, group_id: Vec<u8>) -> Result<(), CryptoError> {
        let inner = self.lock();
        let mut group = inner.load_group(&group_id)?;
        group.clear_pending_commit(inner.provider.storage()).map_err(fail("discard commit"))?;
        inner.save()
    }

    /// The group's current epoch (increases by one with every accepted change).
    pub fn epoch(&self, group_id: Vec<u8>) -> Result<u64, CryptoError> {
        Ok(self.lock().load_group(&group_id)?.epoch().as_u64())
    }

    /// False once this phone has been removed from the group.
    pub fn is_active(&self, group_id: Vec<u8>) -> Result<bool, CryptoError> {
        Ok(self.lock().load_group(&group_id)?.is_active())
    }

    /// Identities of the group's members, e.g. ["user:…", "user:…"].
    pub fn members(&self, group_id: Vec<u8>) -> Result<Vec<String>, CryptoError> {
        let inner = self.lock();
        let group = inner.load_group(&group_id)?;
        Ok(group
            .members()
            .map(|m| String::from_utf8_lossy(m.credential.serialized_content()).into_owned())
            .collect())
    }

    /// 12 groups of 5 digits from both members' signature keys. Two people compare it (or scan each other's
    /// QR) to be sure no one is in the middle; it is the same on both phones.
    pub fn safety_number(&self, group_id: Vec<u8>) -> Result<String, CryptoError> {
        let inner = self.lock();
        let group = inner.load_group(&group_id)?;
        let mut keys: Vec<Vec<u8>> = group.members().map(|m| m.signature_key).collect();
        keys.sort();
        let mut hasher = Sha256::new();
        for key in keys {
            hasher.update(&key);
        }
        let digest = hasher.finalize();
        let mut groups = Vec::new();
        for chunk in digest.chunks(2).take(12) {
            let n = u32::from(chunk[0]) << 8 | u32::from(chunk[1]);
            groups.push(format!("{:05}", n % 100_000));
        }
        Ok(groups.join(" "))
    }
}

fn create_config() -> MlsGroupCreateConfig {
    MlsGroupCreateConfig::builder()
        .ciphersuite(CIPHERSUITE)
        .use_ratchet_tree_extension(true)
        .max_past_epochs(MAX_PAST_EPOCHS)
        .build()
}

impl MlsClient {
    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        // A panic while holding the lock would poison it; recover the data rather than crash the app.
        self.inner.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

impl Inner {
    fn load_group(&self, group_id: &[u8]) -> Result<MlsGroup, CryptoError> {
        MlsGroup::load(self.provider.storage(), &GroupId::from_slice(group_id))
            .map_err(fail("load group"))?
            .ok_or_else(|| CryptoError::Failed { reason: "no such encrypted chat on this phone".into() })
    }

    /// Write the whole state to a temporary file, then rename it over the old one (never half-written).
    fn save(&self) -> Result<(), CryptoError> {
        let values = self.provider.storage.values.read().map_err(fail("storage lock"))?;
        let mut out = Vec::new();
        out.extend_from_slice(FILE_MAGIC);
        write_blob(&mut out, self.identity.as_bytes());
        write_blob(&mut out, self.signer.public());
        out.extend_from_slice(&(values.len() as u64).to_be_bytes());
        for (k, v) in values.iter() {
            write_blob(&mut out, k);
            write_blob(&mut out, v);
        }
        let tmp = self.path.with_extension("tmp");
        let mut file = fs::File::create(&tmp).map_err(fail("write state"))?;
        file.write_all(&out).map_err(fail("write state"))?;
        file.sync_all().map_err(fail("sync state"))?;
        fs::rename(&tmp, &self.path).map_err(fail("replace state"))?;
        Ok(())
    }
}

fn write_blob(out: &mut Vec<u8>, data: &[u8]) {
    out.extend_from_slice(&(data.len() as u64).to_be_bytes());
    out.extend_from_slice(data);
}

type State = (String, Vec<u8>, HashMap<Vec<u8>, Vec<u8>>);

fn read_state(path: &PathBuf) -> Result<State, CryptoError> {
    let mut bytes = Vec::new();
    fs::File::open(path).and_then(|mut f| f.read_to_end(&mut bytes)).map_err(fail("read state"))?;
    let mut cursor = bytes.as_slice();
    let mut magic = [0u8; 6];
    cursor.read_exact(&mut magic).map_err(fail("state header"))?;
    if &magic != FILE_MAGIC {
        return Err(CryptoError::Failed { reason: "unknown state file format".into() });
    }
    let identity = String::from_utf8(read_blob(&mut cursor)?).map_err(fail("state identity"))?;
    let public = read_blob(&mut cursor)?;
    let count = read_u64(&mut cursor)?;
    let mut values = HashMap::with_capacity(count as usize);
    for _ in 0..count {
        let k = read_blob(&mut cursor)?;
        let v = read_blob(&mut cursor)?;
        values.insert(k, v);
    }
    Ok((identity, public, values))
}

fn read_u64(cursor: &mut &[u8]) -> Result<u64, CryptoError> {
    let mut buf = [0u8; 8];
    cursor.read_exact(&mut buf).map_err(fail("state truncated"))?;
    Ok(u64::from_be_bytes(buf))
}

fn read_blob(cursor: &mut &[u8]) -> Result<Vec<u8>, CryptoError> {
    let len = read_u64(cursor)? as usize;
    if len > cursor.len() {
        return Err(CryptoError::Failed { reason: "state truncated".into() });
    }
    let (head, tail) = cursor.split_at(len);
    *cursor = tail;
    Ok(head.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn client(dir: &tempfile::TempDir, name: &str) -> Arc<MlsClient> {
        MlsClient::open(dir.path().join(name).to_string_lossy().into_owned(), format!("user:{name}")).unwrap()
    }

    #[test]
    fn two_people_chat_and_survive_restart() {
        let dir = tempfile::tempdir().unwrap();
        let alice = client(&dir, "alice");
        let bob = client(&dir, "bob");
        let bob_kp = bob.key_packages(3).unwrap().remove(0);
        let group = b"conversation-1".to_vec();

        let welcome = alice.create_direct(group.clone(), bob_kp).unwrap();
        assert_eq!(bob.join(welcome).unwrap(), group);

        let c1 = alice.encrypt(group.clone(), b"Moning! Is the lamp available?".to_vec()).unwrap();
        assert!(!c1.windows(5).any(|w| w == b"Monin"), "ciphertext must not contain the plaintext");
        let d1 = bob.decrypt(group.clone(), c1).unwrap();
        assert_eq!(d1.kind, "application");
        assert_eq!(d1.plaintext.unwrap(), b"Moning! Is the lamp available?");
        assert_eq!(d1.sender, "user:alice");

        // Restart both apps: state comes back from disk.
        drop(alice);
        drop(bob);
        let alice = client(&dir, "alice");
        let bob = client(&dir, "bob");
        let c2 = bob.encrypt(group.clone(), "Yes, K120 with charger".as_bytes().to_vec()).unwrap();
        assert_eq!(alice.decrypt(group.clone(), c2).unwrap().plaintext.unwrap(), b"Yes, K120 with charger");

        assert_eq!(alice.safety_number(group.clone()).unwrap(), bob.safety_number(group.clone()).unwrap());
        let mut members = alice.members(group.clone()).unwrap();
        members.sort();
        assert_eq!(members, vec!["user:alice", "user:bob"]);
        assert!(alice.has_group(group.clone()) && !alice.has_group(b"other".to_vec()));
    }

    #[test]
    fn outsider_cannot_read_and_tampering_fails() {
        let dir = tempfile::tempdir().unwrap();
        let alice = client(&dir, "alice");
        let bob = client(&dir, "bob");
        let eve = client(&dir, "eve");
        let group = b"conversation-2".to_vec();
        let welcome = alice.create_direct(group.clone(), bob.key_packages(1).unwrap().remove(0)).unwrap();
        bob.join(welcome.clone()).unwrap();
        assert!(eve.join(welcome).is_err(), "a Welcome for Bob is useless to anyone else");
        let mut c = alice.encrypt(group.clone(), b"secret".to_vec()).unwrap();
        let last = c.len() - 1;
        c[last] ^= 0x01;
        assert!(bob.decrypt(group, c).is_err(), "a modified message is rejected");
    }

    /// Simulates the delivery service: one accepted change per epoch, delivered in order.
    fn deliver(change: &GroupChange, to: &[&Arc<MlsClient>], group: &[u8]) {
        for c in to {
            let d = c.decrypt(group.to_vec(), change.commit.clone()).unwrap();
            assert!(d.kind == "commit" || d.kind == "removed" || d.kind == "old");
        }
    }

    #[test]
    fn group_add_talk_remove() {
        let dir = tempfile::tempdir().unwrap();
        let (admin, bob, cara, dan) = (client(&dir, "admin"), client(&dir, "bob"), client(&dir, "cara"), client(&dir, "dan"));
        let g = b"group-1".to_vec();
        admin.create_group(g.clone()).unwrap();
        assert_eq!(admin.epoch(g.clone()).unwrap(), 0);

        // Admin adds Bob and Cara in one change.
        let kps = vec![bob.key_packages(1).unwrap().remove(0), cara.key_packages(1).unwrap().remove(0)];
        let add = admin.add_members(g.clone(), kps).unwrap();
        assert_eq!(add.epoch, 0);
        admin.confirm_change(g.clone()).unwrap();
        let welcome = add.welcome.clone().unwrap();
        bob.join(welcome.clone()).unwrap();
        cara.join(welcome).unwrap();
        assert_eq!(bob.members(g.clone()).unwrap().len(), 3);
        // The first commit predates Bob joining: harmless if it reaches him.
        assert_eq!(bob.decrypt(g.clone(), add.commit.clone()).unwrap().kind, "old");

        let hello = cara.encrypt(g.clone(), b"Moning everyone".to_vec()).unwrap();
        assert_eq!(admin.decrypt(g.clone(), hello.clone()).unwrap().plaintext.unwrap(), b"Moning everyone");
        assert_eq!(bob.decrypt(g.clone(), hello).unwrap().sender, "user:cara");

        // Add Dan later: existing members apply the commit, Dan joins from the Welcome.
        let add_dan = admin.add_members(g.clone(), vec![dan.key_packages(1).unwrap().remove(0)]).unwrap();
        assert_eq!(add_dan.epoch, 1);
        admin.confirm_change(g.clone()).unwrap();
        deliver(&add_dan, &[&bob, &cara], &g);
        dan.join(add_dan.welcome.unwrap()).unwrap();
        let m = dan.encrypt(g.clone(), b"Tenkyu for adding me".to_vec()).unwrap();
        assert_eq!(bob.decrypt(g.clone(), m).unwrap().plaintext.unwrap(), b"Tenkyu for adding me");

        // Remove Cara: she learns she was removed and cannot read new messages.
        let rm = admin.remove_members(g.clone(), vec!["user:cara".into()]).unwrap();
        admin.confirm_change(g.clone()).unwrap();
        deliver(&rm, &[&bob, &dan], &g);
        assert_eq!(cara.decrypt(g.clone(), rm.commit.clone()).unwrap().kind, "removed");
        assert!(!cara.is_active(g.clone()).unwrap());
        let secret = bob.encrypt(g.clone(), b"after Cara left".to_vec()).unwrap();
        assert!(cara.decrypt(g.clone(), secret.clone()).is_err());
        assert_eq!(dan.decrypt(g.clone(), secret).unwrap().plaintext.unwrap(), b"after Cara left");
        let mut members = admin.members(g.clone()).unwrap();
        members.sort();
        assert_eq!(members, vec!["user:admin", "user:bob", "user:dan"]);
    }

    #[test]
    fn refused_change_is_discarded_and_late_messages_still_decrypt() {
        let dir = tempfile::tempdir().unwrap();
        let (a, b, c, d) = (client(&dir, "a"), client(&dir, "b"), client(&dir, "c"), client(&dir, "d"));
        let g = b"group-2".to_vec();
        a.create_group(g.clone()).unwrap();
        let add = a.add_members(g.clone(), vec![b.key_packages(1).unwrap().remove(0)]).unwrap();
        a.confirm_change(g.clone()).unwrap();
        b.join(add.welcome.unwrap()).unwrap();

        // B sends a message, then A adds C before B's message arrives at A: still readable (past epoch).
        let early = b.encrypt(g.clone(), b"sent before the change".to_vec()).unwrap();
        let add_c = a.add_members(g.clone(), vec![c.key_packages(1).unwrap().remove(0)]).unwrap();
        // At the same moment B tries to add D, also at epoch 1. The server accepts A's change first and
        // refuses B's (same epoch), so B discards its pending change and applies A's.
        let competing = b.add_members(g.clone(), vec![d.key_packages(1).unwrap().remove(0)]).unwrap();
        assert_eq!(competing.epoch, add_c.epoch);
        b.discard_change(g.clone()).unwrap();
        a.confirm_change(g.clone()).unwrap();
        deliver(&add_c, &[&b], &g);
        assert_eq!(a.decrypt(g.clone(), early).unwrap().plaintext.unwrap(), b"sent before the change");
        assert_eq!(a.epoch(g.clone()).unwrap(), b.epoch(g.clone()).unwrap());
    }

    #[test]
    fn state_file_is_tied_to_one_identity() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("state").to_string_lossy().into_owned();
        drop(MlsClient::open(path.clone(), "user:a".into()).unwrap());
        assert!(MlsClient::open(path, "user:b".into()).is_err());
    }
}
