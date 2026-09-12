export interface TeamPriceElement {
  id: number;
  nowCost: number;
  costChangeStart?: number | null;
}

export interface TeamPriceTransfer {
  elementIn: number;
  elementInCost: number;
  event: number;
  time: string;
}

export interface TeamPricePick {
  element: number;
}

export interface TeamPriceRules {
  sellAtPurchasePrice: boolean;
}

export interface ResolvedTeamPrice {
  purchasePriceTenths: number;
  sellingPriceTenths: number;
}

export function sellingPriceTenths(
  purchasePriceTenths: number,
  currentPriceTenths: number,
  rules: TeamPriceRules,
): number {
  if (
    !Number.isInteger(purchasePriceTenths) ||
    purchasePriceTenths <= 0 ||
    !Number.isInteger(currentPriceTenths) ||
    currentPriceTenths < 0
  ) {
    throw new RangeError("FPL prices must be integer tenths of a million");
  }
  if (rules.sellAtPurchasePrice) return purchasePriceTenths;
  if (currentPriceTenths <= purchasePriceTenths) return currentPriceTenths;
  return (
    purchasePriceTenths +
    Math.floor((currentPriceTenths - purchasePriceTenths) / 2)
  );
}

export function reconcileTeamSellingPrices(
  picks: readonly TeamPricePick[],
  elements: readonly TeamPriceElement[],
  transfers: readonly TeamPriceTransfer[],
  bankTenths: number,
  squadValueTenths: number,
  rules: TeamPriceRules,
): ReadonlyMap<number, ResolvedTeamPrice> | null {
  if (
    !Number.isInteger(bankTenths) ||
    bankTenths < 0 ||
    !Number.isInteger(squadValueTenths) ||
    squadValueTenths < 0
  ) {
    return null;
  }

  const elementsById = new Map(
    elements.map((element) => [element.id, element]),
  );
  const latestTransferByElement = new Map<number, TeamPriceTransfer>();
  for (const transfer of transfers) {
    const previous = latestTransferByElement.get(transfer.elementIn);
    if (
      previous === undefined ||
      transfer.time > previous.time ||
      (transfer.time === previous.time && transfer.event >= previous.event)
    ) {
      latestTransferByElement.set(transfer.elementIn, transfer);
    }
  }

  const resolved = new Map<number, ResolvedTeamPrice>();
  for (const pick of picks) {
    const element = elementsById.get(pick.element);
    if (!element) return null;
    const transfer = latestTransferByElement.get(pick.element);
    const purchasePriceTenths =
      transfer?.elementInCost ??
      (element.costChangeStart === undefined || element.costChangeStart === null
        ? null
        : element.nowCost - element.costChangeStart);
    if (purchasePriceTenths === null || purchasePriceTenths <= 0) return null;
    try {
      resolved.set(pick.element, {
        purchasePriceTenths,
        sellingPriceTenths: sellingPriceTenths(
          purchasePriceTenths,
          element.nowCost,
          rules,
        ),
      });
    } catch {
      return null;
    }
  }

  const saleValue = [...resolved.values()].reduce(
    (total, price) => total + price.sellingPriceTenths,
    0,
  );
  return saleValue + bankTenths === squadValueTenths ? resolved : null;
}
