/**
 * Fold accents so searching "joao" finds "João" and "guehi" finds "Guéhi".
 *
 * A squad is full of names a British keyboard cannot type directly, and an
 * exact-match search quietly hides those players rather than reporting nothing
 * found. NFD splits a letter from its diacritic; the range then drops the
 * combining marks and leaves the base letter.
 */
export function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}
