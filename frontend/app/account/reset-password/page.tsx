import Link from "next/link";
import { ResetPasswordForm } from "./ResetPasswordForm";

// Страница из письма (DRF-2298): uid и token приходят в query. Server component
// читает их и отдаёт форме пропсами — без useSearchParams и Suspense.
type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

function first(v: string | string[] | undefined): string {
  return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
}

export default async function ResetPasswordPage({ searchParams }: Props) {
  const sp = await searchParams;
  return (
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-10 pt-5 sm:px-6 lg:px-8 lg:pt-7">
      <nav aria-label="Хлебные крошки" className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex">
        <Link href="/" className="hover:text-accent">Главная</Link>
        <span aria-hidden>›</span>
        <Link href="/account/login" className="hover:text-accent">Вход</Link>
        <span aria-hidden>›</span>
        <span>Новый пароль</span>
      </nav>
      <div className="mx-auto max-w-[480px] rounded-lg border border-line bg-surface p-5 sm:p-7">
        <ResetPasswordForm uid={first(sp.uid)} token={first(sp.token)} />
      </div>
    </main>
  );
}
