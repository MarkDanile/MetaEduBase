/**
 * BUG-006 #5: FileDetailView "返回" button regression guard.
 *
 * The goBack() function uses router.replace (not router.push) to avoid
 * a race with Vue Query polling during route transition. Also, all
 * action buttons have type="button" to prevent accidental form submit.
 *
 * This file locks:
 *   - goBack uses router.replace("/resource"), not router.push
 *   - "返回" button has type="button"
 *   - "重新初始化" button has type="button"
 *   - "删除" button has type="button"
 */
import { describe, it, expect } from "vitest";
import SFC from "./FileDetailView.vue?raw";

describe("FileDetailView goBack + button type regression (BUG-006 #5)", () => {
  it("goBack uses router.replace, not router.push", () => {
    // The function body should contain router.replace("/resource")
    expect(SFC).toContain('router.replace("/resource")');
    // And should NOT contain router.push in goBack
    // (deleteMutation still uses router.push, which is fine)
    const goBackMatch = SFC.match(
      /function goBack\(\)\s*\{[\s\S]*?\n\}/,
    );
    expect(goBackMatch).not.toBeNull();
    expect(goBackMatch![0]).toContain("router.replace");
    expect(goBackMatch![0]).not.toContain("router.push");
  });

  it('"返回" button has type="button"', () => {
    // Find the goBack button and check it has type="button"
    const goBackButtonMatch = SFC.match(
      /<button[^>]*@click="goBack"[^>]*>/,
    );
    expect(goBackButtonMatch).not.toBeNull();
    expect(goBackButtonMatch![0]).toContain('type="button"');
  });

  it('"重新初始化" button has type="button"', () => {
    const reinitButtonMatch = SFC.match(
      /<button[^>]*@click="reinitializeMutation\.mutate\(\)"[^>]*>/,
    );
    expect(reinitButtonMatch).not.toBeNull();
    expect(reinitButtonMatch![0]).toContain('type="button"');
  });

  it('"删除" button has type="button"', () => {
    const deleteButtonMatch = SFC.match(
      /<button[^>]*@click="showDelete = true"[^>]*>/,
    );
    expect(deleteButtonMatch).not.toBeNull();
    expect(deleteButtonMatch![0]).toContain('type="button"');
  });
});
