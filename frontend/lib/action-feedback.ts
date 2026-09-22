// Шина «действие покупателя удалось» — для микроанимаций иконок шапки.
//
// Сердечко, столбики сравнения и корзина в шапке оживают только от реального
// успешного добавления товара: гость сохранил в браузер, сервер подтвердил,
// корзина ответила снимком. Издатели — сами точки успеха (lib/wishlist-storage,
// lib/compare, CartProvider), а не кнопки: тогда карточка, быстрый просмотр,
// страница товара и сравнение покрыты одним проводом, и ни одна новая кнопка
// не забудет «дёрнуть шапку».
//
// Чего здесь намеренно нет: загрузки списка, восстановления из localStorage,
// storage-событий соседней вкладки, переноса гостевого списка при входе,
// удаления и ошибок. Всё это меняет счётчик, но не «успешное добавление».
//
// Модуль без React и без window при импорте — безопасен для SSR.

export type ActionKind = "wishlist" | "compare" | "cart";

type Listener = (kind: ActionKind) => void;

const listeners = new Set<Listener>();

/** Сообщить, что товар успешно добавлен. Звать только из обработчиков и промисов, не из рендера. */
export function emitActionSuccess(kind: ActionKind): void {
  for (const listener of listeners) {
    try {
      listener(kind);
    } catch (error) {
      // Слушатель — декоративный. Его сбой не должен превращаться в откат
      // оптимистичного состояния у издателя (`.then(emit).catch(rollback)`).
      console.error(error);
    }
  }
}

export function subscribeActionSuccess(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
