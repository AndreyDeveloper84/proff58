import { redirect } from "next/navigation";

// Избранное переехало из кабинета на витрину (/wishlist): сохранять товары
// можно и без аккаунта. Редирект оставлен ради сохранённых ссылок и закладок —
// адрес кабинета годами мог лежать у людей в истории.
export default function AccountWishlistRedirect() {
  redirect("/wishlist");
}
