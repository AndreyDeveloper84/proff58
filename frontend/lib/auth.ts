// API клиент аутентификации (#330)

const API = process.env.NEXT_PUBLIC_API_BASE || "";

export async function login(phone: string, password: string) {
  const res = await fetch(`${API}/api/account/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ phone, password }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Ошибка входа");
  return res.json();
}

export async function register(data: {
  phone: string;
  password: string;
  full_name?: string;
  email?: string;
}) {
  const res = await fetch(`${API}/api/account/register/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Ошибка регистрации");
  return res.json();
}

export async function logout() {
  await fetch(`${API}/api/account/logout/`, {
    method: "POST",
    credentials: "include",
  });
}

export async function getMe() {
  const res = await fetch(`${API}/api/account/me/`, { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}

export async function otpLogin(phone: string, otp: string) {
  const res = await fetch(`${API}/api/account/otp-login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ phone, otp }),
  });
  if (!res.ok) throw new Error((await res.json()).detail || "Ошибка");
  return res.json();
}

export async function getOrders() {
  const res = await fetch(`${API}/api/orders/`, { credentials: "include" });
  if (!res.ok) return [];
  return res.json();
}

export async function getWishlist() {
  const res = await fetch(`${API}/api/account/wishlist/`, {
    credentials: "include",
  });
  if (!res.ok) return [];
  return res.json();
}
