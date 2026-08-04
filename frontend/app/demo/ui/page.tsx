import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState, SuccessState } from "@/components/ui/states";
import { Textarea } from "@/components/ui/textarea";

import { ThemeFrame } from "../_components/ThemeFrame";

// SP2 kitchen-sink (#39): визуальная проверка базовых токенов и компонентов.
// Не входит в продакшн-навигацию — служит согласованным эталоном дизайн-системы.

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="font-display text-lg text-ink">{title}</h2>
      {children}
    </section>
  );
}

const TOKENS = [
  ["canvas", "bg-canvas"],
  ["surface", "bg-surface"],
  ["raised", "bg-raised"],
  // accent — то, что нажимают; brand — состояние товара. Порядок как в globals.css.
  ["accent", "bg-accent"],
  ["brand", "bg-brand"],
  ["danger", "bg-danger"],
  ["rating", "bg-rating"],
  ["hit", "bg-hit"],
  ["max", "bg-max"],
  ["info", "bg-info"],
];

export default function UiKitPage() {
  return (
    <ThemeFrame>
      <div className="mx-auto max-w-4xl space-y-12 p-8">
        <header className="space-y-1">
          <h1 className="font-display text-2xl text-ink">SP2 · Дизайн-система</h1>
          <p className="text-sm text-ink-2">
            Базовые токены и компоненты витрины «Профессионал».
          </p>
        </header>

      <Section title="Цветовые токены">
        <div className="flex flex-wrap gap-3">
          {TOKENS.map(([name, cls]) => (
            <div key={name} className="text-center">
              <div className={`h-14 w-20 rounded-md border border-line ${cls}`} />
              <span className="text-xs text-ink-3">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Кнопки">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="accent">Оформить</Button>
          <Button variant="outline">В корзину</Button>
          <Button variant="ghost">Подробнее</Button>
          <Button variant="accent" disabled>
            Недоступно
          </Button>
        </div>
      </Section>

      <Section title="Бейджи">
        <div className="flex flex-wrap gap-2">
          <Badge variant="hit">Хит</Badge>
          <Badge variant="sale">−16%</Badge>
          <Badge variant="new">Новинка</Badge>
          <Badge variant="neutral">В наличии</Badge>
        </div>
      </Section>

      <Section title="Поля формы">
        <Card className="max-w-md space-y-4">
          <Field label="Телефон" required hint="Для связи по заказу">
            {(p) => <Input {...p} placeholder="+7 900 000-00-00" />}
          </Field>
          <Field label="E-mail" error="Некорректный e-mail">
            {(p) => <Input {...p} defaultValue="bad@" />}
          </Field>
          <Field label="Комментарий">
            {(p) => <Textarea {...p} placeholder="Пожелания к заказу" />}
          </Field>
        </Card>
      </Section>

      <Section title="Состояния">
        <div className="grid gap-4 sm:grid-cols-2">
          <Card pad="none">
            <LoadingState />
          </Card>
          <Card pad="none">
            <EmptyState
              title="Ничего не найдено"
              description="Измените фильтры или запрос."
              action={<Button variant="outline">Сбросить фильтры</Button>}
            />
          </Card>
          <Card pad="none">
            <ErrorState action={<Button variant="outline">Повторить</Button>} />
          </Card>
          <Card pad="none">
            <SuccessState
              title="Заказ оформлен"
              description="Мы свяжемся с вами для подтверждения."
              action={<Button variant="accent">Мои заказы</Button>}
            />
          </Card>
        </div>
      </Section>
      </div>
    </ThemeFrame>
  );
}
