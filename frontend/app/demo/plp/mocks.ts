// Mock-данные для hi-fi макета PLP (категория «Шуруповёрты»). Только для /demo/plp.

export type PlpStock = "in" | "low" | "order" | "out" | "no_price";

export type PlpProduct = {
  id: number;
  brand: string;
  name: string; // витринное название (2 строки)
  specs: string; // краткие ТТХ одной строкой
  price: number | null;
  oldPrice?: number;
  discountPct?: number;
  stock: PlpStock;
  noPhoto?: boolean;
};

export const PLP_PRODUCTS: PlpProduct[] = [
  {
    id: 1,
    brand: "Makita",
    name: "Аккумуляторный шуруповёрт Makita DDF485RFJ 18В",
    specs: "18 В · 50 Н·м · 2×3.0 А·ч · кейс",
    price: 12990,
    oldPrice: 15290,
    discountPct: 15,
    stock: "in",
  },
  {
    id: 2,
    brand: "Makita",
    name: "Аккумуляторный шуруповёрт Makita DDF482RME 18В",
    specs: "18 В · 62 Н·м · 2×4.0 А·ч · кейс",
    price: 10490,
    stock: "in",
  },
  {
    id: 3,
    brand: "HiKOKI",
    name: "Аккумуляторный шуруповёрт HiKOKI DS18DDW2Z 18В",
    specs: "18 В · 55 Н·м · 2×2.0 А·ч",
    price: 9990,
    stock: "in",
  },
  {
    id: 4,
    brand: "DeWALT",
    name: "Аккумуляторный шуруповёрт DeWALT DCD791D2 18В",
    specs: "18 В · 70 Н·м · 2×4.0 А·ч · кейс",
    price: 17990,
    oldPrice: 19990,
    discountPct: 10,
    stock: "low",
  },
  {
    id: 5,
    brand: "Bosch",
    name: "Аккумуляторный шуруповёрт Bosch GSR 18V-50 18В",
    specs: "18 В · 50 Н·м · 2×2.0 А·ч · кейс",
    price: 13990,
    stock: "order",
  },
  {
    id: 6,
    brand: "Metabo",
    name: "Аккумуляторный шуруповёрт Metabo BS 18 LTX BL I 18В",
    specs: "18 В · 60 Н·м · 2×4.0 А·ч · кейс",
    price: 21990,
    oldPrice: 24990,
    discountPct: 12,
    stock: "in",
  },
  {
    id: 7,
    brand: "Milwaukee",
    name: "Аккумуляторный ударный шуруповёрт Milwaukee M18 FPD2-502X 18В Li-Ion REDLITHIUM-ION",
    specs: "18 В · 135 Н·м · 2×5.0 А·ч · кейс",
    price: 26990,
    stock: "order",
  },
  {
    id: 8,
    brand: "HiKOKI",
    name: "Аккумуляторный шуруповёрт HiKOKI DS18DDW2Z 18В",
    specs: "18 В · 55 Н·м · 2×2.0 А·ч",
    price: 8990,
    stock: "out",
  },
  {
    id: 9,
    brand: "Makita",
    name: "Аккумуляторный шуруповёрт Makita DHP487Z 18В",
    specs: "18 В · 40 Н·м · без АКБ",
    price: null,
    stock: "no_price",
  },
  {
    id: 10,
    brand: "ЗУБР",
    name: "Аккумуляторный шуруповёрт ЗУБР ДШ-18-2-Ли КНМ4",
    specs: "18 В · 45 Н·м · 2×2.0 А·ч",
    price: 6990,
    stock: "in",
    noPhoto: true,
  },
  {
    id: 11,
    brand: "Интерскол",
    name: "Аккумуляторный шуруповёрт Интерскол ДА-18ЭР",
    specs: "18 В · 45 Н·м · 2×1.5 А·ч",
    price: 7890,
    stock: "in",
  },
  {
    id: 12,
    brand: "Ryobi",
    name: "Аккумуляторный шуруповёрт Ryobi R18DD3-0 18В",
    specs: "18 В · 50 Н·м · без АКБ",
    price: 6990,
    stock: "in",
  },
];

// Фасеты левого сайдбара.
export const PLP_AVAILABILITY = [
  { label: "В наличии", count: 92, checked: true },
  { label: "Мало осталось", count: 18, checked: false },
  { label: "Под заказ", count: 12, checked: false },
  { label: "Нет в наличии", count: 4, checked: false },
];

export const PLP_BRANDS = [
  { label: "Makita", count: 36, checked: true },
  { label: "DeWALT", count: 28, checked: false },
  { label: "Bosch", count: 24, checked: false },
  { label: "Metabo", count: 18, checked: false },
  { label: "Milwaukee", count: 14, checked: false },
];

export const PLP_VOLTAGE = [
  { label: "12 В", count: 8 },
  { label: "14.4 В", count: 96 },
  { label: "18 В", count: 92, checked: true },
  { label: "20 В", count: 14 },
  { label: "22 В", count: 18 },
];

// Активные чипы (выбранные фильтры) над сеткой.
export const PLP_ACTIVE_CHIPS = ["В наличии", "18 В", "Кейс в комплекте", "Бесщёточный"];

// Свёрнутые группы фасетов (только заголовки).
export const PLP_COLLAPSED_GROUPS = [
  "Аккумуляторы в комплекте",
  "Бесщёточный двигатель",
  "Кейс в комплекте",
];
