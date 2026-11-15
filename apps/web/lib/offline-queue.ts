export type QueuedRequest = { id: string; ownerId?: string; path: string; method: string; body: string; createdAt: string; lastError?: string };

const DB_NAME = "terravanta-offline-v1";
const STORE = "requests";

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
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function enqueue(path: string, method: string, body: string, ownerId = queueOwnerId()): Promise<QueuedRequest> {
  const entry: QueuedRequest = { id: crypto.randomUUID(), ownerId, path, method, body, createdAt: new Date().toISOString() };
  const db = await openQueue();
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).put(entry);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
  return entry;
}

export async function readQueue(ownerId?: string): Promise<QueuedRequest[]> {
  const db = await openQueue();
  const records = await new Promise<QueuedRequest[]>((resolve, reject) => {
    const request = db.transaction(STORE, "readonly").objectStore(STORE).getAll();
    request.onsuccess = () => resolve(request.result as QueuedRequest[]);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return records.filter((record) => ownerId === undefined || record.ownerId === ownerId).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function removeQueued(id: string): Promise<void> {
  const db = await openQueue();
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE, "readwrite");
    transaction.objectStore(STORE).delete(id);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
}

export async function updateQueueError(id: string, message: string): Promise<void> {
  const db = await openQueue();
  const transaction = db.transaction(STORE, "readwrite");
  const store = transaction.objectStore(STORE);
  const request = store.get(id);
  request.onsuccess = () => request.result && store.put({ ...request.result, lastError: message });
  await new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
}
