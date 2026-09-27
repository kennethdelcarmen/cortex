export type MoneyPeriodId = "2026-09" | "2026-08";

export type MoneyAccount = {
  id: string;
  name: string;
  type: "Checking" | "Savings" | "Cash";
  institution: string;
  lastFour: string | null;
  balance: number;
};

export type MoneyBudget = {
  id: string;
  category: string;
  amount: number;
  spent: number;
};

export type MoneyTransaction = {
  id: string;
  date: string;
  payee: string;
  category: string;
  accountId: string;
  amount: number;
};

export type MoneyPeriod = {
  id: MoneyPeriodId;
  label: string;
  balance: number;
  income: number;
  spending: number;
  accounts: MoneyAccount[];
  budgets: MoneyBudget[];
  transactions: MoneyTransaction[];
};

export const moneyPeriods: MoneyPeriod[] = [
  {
    id: "2026-09",
    label: "September 2026",
    balance: 86_350,
    income: 72_500,
    spending: 43_220,
    accounts: [
      {
        id: "daily-checking",
        name: "Daily checking",
        type: "Checking",
        institution: "Harbor Bank",
        lastFour: "4821",
        balance: 58_400,
      },
      {
        id: "quiet-savings",
        name: "Quiet savings",
        type: "Savings",
        institution: "Harbor Bank",
        lastFour: "1097",
        balance: 25_850,
      },
      {
        id: "wallet-cash",
        name: "Wallet cash",
        type: "Cash",
        institution: "On hand",
        lastFour: null,
        balance: 2_100,
      },
    ],
    budgets: [
      { id: "housing", category: "Housing", amount: 22_000, spent: 18_000 },
      {
        id: "food-household",
        category: "Food & household",
        amount: 12_000,
        spent: 8_420,
      },
      { id: "transport", category: "Transport", amount: 8_000, spent: 4_600 },
      { id: "health", category: "Health", amount: 6_500, spent: 2_100 },
      { id: "personal", category: "Personal", amount: 10_000, spent: 5_300 },
      { id: "dining", category: "Dining out", amount: 4_000, spent: 4_800 },
    ],
    transactions: [
      {
        id: "sep-market",
        date: "Sep 24",
        payee: "Mercury Market",
        category: "Food & household",
        accountId: "daily-checking",
        amount: -1_450,
      },
      {
        id: "sep-utilities",
        date: "Sep 21",
        payee: "Northstar Utilities",
        category: "Housing",
        accountId: "daily-checking",
        amount: -3_900,
      },
      {
        id: "sep-payroll",
        date: "Sep 18",
        payee: "Payroll",
        category: "Income",
        accountId: "daily-checking",
        amount: 72_500,
      },
      {
        id: "sep-dining",
        date: "Sep 16",
        payee: "Lantern Table",
        category: "Dining out",
        accountId: "daily-checking",
        amount: -1_180,
      },
      {
        id: "sep-pharmacy",
        date: "Sep 12",
        payee: "Dahlia Pharmacy",
        category: "Health",
        accountId: "wallet-cash",
        amount: -920,
      },
    ],
  },
  {
    id: "2026-08",
    label: "August 2026",
    balance: 71_980,
    income: 68_000,
    spending: 46_320,
    accounts: [
      {
        id: "daily-checking",
        name: "Daily checking",
        type: "Checking",
        institution: "Harbor Bank",
        lastFour: "4821",
        balance: 46_780,
      },
      {
        id: "quiet-savings",
        name: "Quiet savings",
        type: "Savings",
        institution: "Harbor Bank",
        lastFour: "1097",
        balance: 23_100,
      },
      {
        id: "wallet-cash",
        name: "Wallet cash",
        type: "Cash",
        institution: "On hand",
        lastFour: null,
        balance: 2_100,
      },
    ],
    budgets: [
      { id: "housing", category: "Housing", amount: 22_000, spent: 22_000 },
      {
        id: "food-household",
        category: "Food & household",
        amount: 11_000,
        spent: 9_700,
      },
      { id: "transport", category: "Transport", amount: 8_000, spent: 7_240 },
      { id: "health", category: "Health", amount: 6_500, spent: 3_800 },
      { id: "personal", category: "Personal", amount: 9_000, spent: 6_500 },
      { id: "dining", category: "Dining out", amount: 4_000, spent: 5_080 },
    ],
    transactions: [
      {
        id: "aug-rent",
        date: "Aug 29",
        payee: "Harbor Homes",
        category: "Housing",
        accountId: "daily-checking",
        amount: -22_000,
      },
      {
        id: "aug-market",
        date: "Aug 24",
        payee: "Mercury Market",
        category: "Food & household",
        accountId: "daily-checking",
        amount: -1_920,
      },
      {
        id: "aug-payroll",
        date: "Aug 18",
        payee: "Payroll",
        category: "Income",
        accountId: "daily-checking",
        amount: 68_000,
      },
      {
        id: "aug-transit",
        date: "Aug 13",
        payee: "Metro Transit",
        category: "Transport",
        accountId: "quiet-savings",
        amount: -740,
      },
      {
        id: "aug-dining",
        date: "Aug 8",
        payee: "Lantern Table",
        category: "Dining out",
        accountId: "daily-checking",
        amount: -1_420,
      },
    ],
  },
];

export const moneyPeriodOptions = moneyPeriods.map(({ id, label }) => ({ id, label }));
