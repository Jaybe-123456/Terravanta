export type QueuedRequest = {
  id: string;
  ownerId: string;
  path: string;
  method: string;
  body: string;
  createdAt: string;
  lastError?: string;
};

type StoredRequest = {
  id: string;
  ownerHash: string;
  createdAt: string;
  iv: Uint8Array<ArrayBuffer>;
  ciphertext: ArrayBuffer;
  lastError?: string;
  // Version 1 entries are migrated to encrypted payloads on first read.
  ownerId?: string;
  path?: string;
  method?: string;
  body?: string;
};

const DB_NAME = "terravanta-offline-v1";
const DB_VERSION = 2;
const REQUESTS = "requests";
const KEYS = "encryption-keys";

export function queueOwnerId(): string {
  try {
    const accountId = localStorage.getItem("terravanta-account-id-v1");
    if (accountId) return accountId;
    const demoSession = JSON.parse(localStorage.getItem("terravanta-session-v1") || "null");
    return demoSession?.user?.id || "device-local";
  } catch { return "device-local"; }
}

function openQueue(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(REQUESTS)) db.createObjectStore(REQUESTS, { keyPath: "id" });
      if (!db.objectStoreNames.contains(KEYS)) db.createObjectStore(KEYS);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function ownerHash(ownerId: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ownerId));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function keyForOwner(hash: string): Promise<CryptoKey> {
  const db = await openQueue();
  const existing = await new Promise<CryptoKey | undefined>((resolve, reject) => {
    const request = db.transaction(KEYS, "readonly").objectStore(KEYS).get(hash);
    request.onsuccess = () => resolve(request.result as CryptoKey | undefined);
    request.onerror = () => reject(request.error);
  });
  db.close();
  if (existing) return existing;

  const generated = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  const writeDb = await openQueue();
  const key = await new Promise<CryptoKey>((resolve, reject) => {
    const transaction = writeDb.transaction(KEYS, "readwrite");
    const store = transaction.objectStore(KEYS);
    const request = store.get(hash);
    let result = generated;
    request.onsuccess = () => {
      if (request.result) result = request.result as CryptoKey;
      else store.put(generated, hash);
    };
    transaction.oncomplete = () => resolve(result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error("Offline key storage was aborted"));
  });
  writeDb.close();
  return key;
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error("Offline storage transaction was aborted"));
  });
}

async function encryptPayload(ownerId: string, payload: { path: string; method: string; body: string }): Promise<Pick<StoredRequest, "ownerHash" | "iv" | "ciphertext">> {
  const hash = await ownerHash(ownerId);
  const key = await keyForOwner(hash);
  const iv = new Uint8Array(new ArrayBuffer(12));
  crypto.getRandomValues(iv);
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify({ ...payload, ownerId })));
  return { ownerHash: hash, iv, ciphertext };
}

async function decryptPayload(record: StoredRequest): Promise<{ ownerId: string; path: string; method: string; body: string }> {
  if (record.ownerId && record.path !== undefined && record.method && record.body !== undefined) {
    const migrated = await encryptPayload(record.ownerId, { path: record.path, method: record.method, body: record.body });
    const next: StoredRequest = { id: record.id, createdAt: record.createdAt, lastError: record.lastError, ...migrated };
    const db = await openQueue();
    const transaction = db.transaction(REQUESTS, "readwrite");
    transaction.objectStore(REQUESTS).put(next);
    await transactionDone(transaction);
    db.close();
    return { ownerId: record.ownerId, path: record.path, method: record.method, body: record.body };
  }

  const key = await keyForOwner(record.ownerHash);
  const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv: record.iv }, key, record.ciphertext);
  const payload = JSON.parse(new TextDecoder().decode(plaintext)) as { ownerId: string; path: string; method: string; body: string };
  return payload;
}

export async function requestPersistentStorage(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.storage?.persist) return false;
  try {
    if (await navigator.storage.persisted()) return true;
    return await navigator.storage.persist();
  } catch { return false; }
}

export async function enqueue(path: string, method: string, body: string, ownerId = queueOwnerId()): Promise<QueuedRequest & { storagePersistent: boolean }> {
  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const encrypted = await encryptPayload(ownerId, { path, method, body });
  const db = await openQueue();
  // Durability options are not implemented in every supported browser. Keep
  // the queue usable there while requesting strict durability where available.
  let transaction: IDBTransaction;
  try { transaction = db.transaction(REQUESTS, "readwrite", { durability: "strict" }); }
  catch { transaction = db.transaction(REQUESTS, "readwrite"); }
  transaction.objectStore(REQUESTS).put({ id, createdAt, ...encrypted } satisfies StoredRequest);
  await transactionDone(transaction);
  db.close();
  const storagePersistent = await requestPersistentStorage();
  return { id, ownerId, path, method, body, createdAt, storagePersistent };
}

export async function readQueue(ownerId?: string): Promise<QueuedRequest[]> {
  const db = await openQueue();
  const records = await new Promise<StoredRequest[]>((resolve, reject) => {
    const request = db.transaction(REQUESTS, "readonly").objectStore(REQUESTS).getAll();
    request.onsuccess = () => resolve(request.result as StoredRequest[]);
    request.onerror = () => reject(request.error);
  });
  db.close();
  const ownerScope = ownerId === undefined ? undefined : await ownerHash(ownerId);
  const result: QueuedRequest[] = [];
  for (const record of records) {
    const legacyOwnerId = record.ownerId;
    const hash = record.ownerHash || (legacyOwnerId ? await ownerHash(legacyOwnerId) : "");
    if (ownerScope && hash !== ownerScope) continue;
    try {
      const payload = await decryptPayload(record);
      const resolvedOwner = legacyOwnerId || (ownerScope ? ownerId! : payload.ownerId);
      result.push({
        id: record.id, ownerId: resolvedOwner, path: payload.path, method: payload.method,
        body: payload.body, createdAt: record.createdAt, lastError: record.lastError,
      });
    } catch {
      // Never misreport an undecryptable request as an empty queue or replay it as an empty write.
      throw new Error("An encrypted offline record could not be unlocked. Keep this browser profile and contact support before clearing site data.");
    }
  }
  return result.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function removeQueued(id: string): Promise<void> {
  const db = await openQueue();
  const transaction = db.transaction(REQUESTS, "readwrite");
  transaction.objectStore(REQUESTS).delete(id);
  await transactionDone(transaction);
  db.close();
}

export async function updateQueueError(id: string, message: string): Promise<void> {
  const db = await openQueue();
  const transaction = db.transaction(REQUESTS, "readwrite");
  const store = transaction.objectStore(REQUESTS);
  const request = store.get(id);
  request.onsuccess = () => request.result && store.put({ ...request.result, lastError: message.slice(0, 240) });
  await transactionDone(transaction);
  db.close();
}
