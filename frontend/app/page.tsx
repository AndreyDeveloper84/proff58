export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col items-center justify-center gap-6 p-8 text-center">
      <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        Профессионал
      </h1>
      <p className="text-ink-3">Шаблон витрины (PLP) на фикстурах.</p>
      <a
        href="/catalog/perforatory"
        className="rounded-md bg-accent px-4 py-2 font-medium text-accent-ink"
      >
        Открыть категорию «Перфораторы»
      </a>
    </main>
  );
}
