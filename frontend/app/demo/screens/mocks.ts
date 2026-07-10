import type { Product } from "@/lib/types";

// Mock-данные для галереи экранов MVP (#40). Только для /demo/screens — не прод.
export const MOCK_PRODUCTS: Product[] = [
  {
    id: 1,
    slug: "bosch-gbh-2-26",
    name: "Перфоратор Bosch GBH 2-26 DRE SDS-Plus",
    brand: "Bosch",
    image: "/sample-tool.svg",
    rating: 4.7,
    reviews: 128,
    specs: [
      { label: "Мощность", value: "800 Вт" },
      { label: "Энергия удара", value: "2.7 Дж" },
      { label: "Патрон", value: "SDS-Plus" },
    ],
    energy: "2.7 Дж",
    price: { final: 12990, old: 15490, discountPct: 16, currency: "RUB" },
    stock: "in",
    stockQty: 8,
    badges: ["hit", "sale"],
  },
  {
    id: 2,
    slug: "makita-hp1631",
    name: "Дрель ударная Makita HP1631",
    brand: "Makita",
    image: "/sample-tool.svg",
    rating: 4.5,
    reviews: 64,
    specs: [
      { label: "Мощность", value: "710 Вт" },
      { label: "Патрон", value: "БЗП 13 мм" },
    ],
    price: { final: 5490, currency: "RUB" },
    stock: "order",
    badges: ["new"],
  },
  {
    id: 3,
    slug: "dewalt-dwe4157",
    name: "УШМ DeWalt DWE4157 125 мм",
    brand: "DeWalt",
    image: "/sample-tool.svg",
    rating: 4.8,
    reviews: 212,
    specs: [
      { label: "Мощность", value: "900 Вт" },
      { label: "Диск", value: "125 мм" },
    ],
    price: { final: 7890, currency: "RUB" },
    stock: "out",
    badges: [],
  },
];

export const MOCK_FACETS = [
  { title: "Бренд", options: ["Bosch (42)", "Makita (38)", "DeWalt (25)"] },
  { title: "Мощность, Вт", options: ["до 700", "700–900", "от 900"] },
  { title: "Патрон", options: ["SDS-Plus", "БЗП", "Ключевой"] },
];

export const MOCK_CATEGORIES = [
  "Перфораторы",
  "Дрели и шуруповёрты",
  "УШМ (болгарки)",
  "Лобзики",
  "Пилы",
  "Расходники",
];
