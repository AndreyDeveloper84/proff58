// Подписи способа получения заказа — общий словарь витрины (кабинет, «Спасибо»).

export const DELIVERY_METHOD_LABELS: Record<string, string> = {
  courier: "Курьерская доставка",
  delivery: "Доставка",
  pickup: "Самовывоз",
  transport_company: "Транспортная компания",
  cdek_pvz: "СДЭК, пункт выдачи",
  cdek_courier: "СДЭК, курьер",
};

export function deliveryMethodLabel(method: string): string {
  return DELIVERY_METHOD_LABELS[method] ?? method;
}
