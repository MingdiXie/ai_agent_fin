const CLIENT_ID_KEY = 'investor-lens-client-id';

export function getClientId() {
  let clientId = localStorage.getItem(CLIENT_ID_KEY);
  if (!clientId) {
    clientId =
      crypto.randomUUID?.() ||
      `client-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(CLIENT_ID_KEY, clientId);
  }
  return clientId;
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchUsage(token) {
  const res = await fetch('/api/usage', {
    headers: {
      'X-Client-Id': getClientId(),
      ...authHeaders(token),
    },
  });
  if (!res.ok) throw new Error('Could not load usage');
  return res.json();
}

export async function startCheckout(token) {
  const res = await fetch('/api/billing/checkout', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(token),
    },
    body: JSON.stringify({ client_id: getClientId() }),
  });
  const json = await res.json();
  if (!res.ok) {
    const message = typeof json.detail === 'string' ? json.detail : 'Checkout is not configured yet';
    throw new Error(message);
  }
  window.location.href = json.url;
}
