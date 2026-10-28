/**
 * REQ-064 S1b-1：共享层控件状态矩阵（G2）。
 *
 * spec §2.1 要求共享层覆盖 default、hover、focus-visible、active/selected、
 * disabled、loading、empty、error、success、无权限等**适用**状态，并给出
 * 表格、表单、卡片、菜单、确认弹窗的统一契约；同时明确「某状态无真实能力
 * 支撑时记录门控或不适用原因，**不以静态示例补造生产状态**」。
 *
 * 本文件是该契约的**机器可读**事实源：
 *
 * - 每行 = 一个「面 × 共享控件」，每列 = spec §2.1 列出的一个状态；
 * - `implemented` 的状态必须给出**真实存在于** `src/assets/css/components.css`
 *   的选择器，`not-applicable` / `gated` 的状态必须写明原因；
 * - `src/constants/__tests__/sharedLayerContract.spec.ts` 会强制本表与 CSS
 *   一致（选择器缺失即失败；缺原因即失败；漏状态即失败），因此契约不会
 *   与实现悄悄漂移。
 *
 * 本切片**不新建平行设计系统**：只登记共享层已拥有的 `ui-*` 类；表格与菜单
 * 尚无共享类，按 spec 记为门控项，交由后续页面切片收敛，不在本切片补造。
 */

/** spec §2.1 列出的共享层适用状态。 */
export const SHARED_LAYER_STATES = [
  "default",
  "hover",
  "focus-visible",
  "active",
  "selected",
  "disabled",
  "loading",
  "empty",
  "error",
  "success",
  "no-permission",
] as const;

export type SharedLayerState = (typeof SHARED_LAYER_STATES)[number];

/** spec §2.1 要求统一契约的五类界面载体。 */
export const SHARED_LAYER_SURFACES = [
  "表单",
  "卡片",
  "表格",
  "菜单",
  "确认弹窗",
] as const;

export type SharedLayerSurface = (typeof SHARED_LAYER_SURFACES)[number];

/** 单个状态的支持方式。 */
export type StateSupport =
  /** 已实现：选择器必须真实存在于 components.css */
  | { kind: "implemented"; selectors: string[] }
  /** 不适用：该控件没有此状态的真实语义 */
  | { kind: "not-applicable"; reason: string }
  /** 门控：需要真实能力或后续切片才可建立，本切片不补造 */
  | { kind: "gated"; reason: string };

/** 一个「面 × 共享控件」的状态契约。 */
export interface ControlContract {
  /** 界面载体 */
  surface: SharedLayerSurface;
  /** 共享控件（共享类名或共享组件名） */
  control: string;
  /** 状态 → 支持方式（必须覆盖全部状态） */
  states: Record<SharedLayerState, StateSupport>;
}

const implemented = (...selectors: string[]): StateSupport => ({
  kind: "implemented",
  selectors,
});

const notApplicable = (reason: string): StateSupport => ({
  kind: "not-applicable",
  reason,
});

const gated = (reason: string): StateSupport => ({
  kind: "gated",
  reason,
});

/**
 * 共享层控件状态契约矩阵。
 *
 * 选择器书写约定：与 `src/assets/css/components.css` 中的**字面**一致，
 * 便于契约测试直接做子串比对（CSS 中换行会被测试归一化为空格）。
 */
export const SHARED_LAYER_CONTRACT: ControlContract[] = [
  {
    surface: "表单",
    control: ".ui-input",
    states: {
      default: implemented(".ui-input"),
      hover: implemented(
        '.ui-input:hover:not(:disabled):not([aria-readonly="true"])',
      ),
      "focus-visible": implemented(".ui-input:focus-visible"),
      active: notApplicable(
        "输入框无独立按下态；按下反馈由 hover 与 focus 覆盖，避免与 focus 环叠加冲突",
      ),
      selected: notApplicable(
        "输入框无选中态语义；文本选区由浏览器原生选择表达，不另建共享态",
      ),
      disabled: implemented(".ui-input:disabled"),
      loading: gated(
        "输入框本身无法呈现加载指示（::after 不可用于原生输入控件）；真实 loading 由按钮与容器承担，待共享层建立统一加载契约后再补",
      ),
      empty: notApplicable(
        "输入框无空态；列表空态由 EmptyState 组件承担",
      ),
      error: implemented(".ui-input.is-error"),
      success: implemented(".ui-input.is-success"),
      "no-permission": implemented('.ui-input[aria-readonly="true"]'),
    },
  },
  {
    surface: "表单",
    control: ".ui-btn（primary / ghost / danger 变体）",
    states: {
      default: implemented(".ui-btn"),
      hover: implemented(
        ".ui-btn-primary:hover",
        ".ui-btn-ghost:hover",
        ".ui-btn-danger:hover",
      ),
      "focus-visible": implemented(".ui-btn:focus-visible"),
      active: implemented(".ui-btn-primary:active"),
      selected: gated(
        "按钮没有选中态语义；选中语义应由 toggle / tab 类控件承担，共享层尚未建立该契约",
      ),
      disabled: implemented(".ui-btn-primary:disabled"),
      loading: gated(
        "按钮加载态需要真实能力（进行中的任务标识与取消入口）；现有 LoadingSpinner 未与按钮绑定，本切片不补造静态加载样式",
      ),
      empty: notApplicable("按钮是动作触发器，没有空态；空态由容器承担"),
      error: notApplicable(
        "按钮错误态由 danger 变体与确认弹窗承担，按钮本身不承担错误语义",
      ),
      success: notApplicable("按钮是动作触发器，没有成功态；成功反馈由内部提示承担"),
      "no-permission": gated(
        "无权限态需要权限层下发 aria-disabled / 禁用原因，共享层尚未建立该契约；本切片不臆造权限来源",
      ),
    },
  },
  {
    surface: "卡片",
    control: ".ui-panel（.ui-panel-static / .ui-panel-interactive）",
    states: {
      default: implemented(".ui-panel"),
      hover: gated(
        "静态面板不响应 hover（.ui-panel-static 已提供显式静态入口），可交互面板沿用 .ui-panel:hover；未迁移使用点的历史抬升行为由页面切片按所有权逐步收敛",
      ),
      "focus-visible": implemented(".ui-panel-interactive:focus-visible"),
      active: notApplicable("面板本身没有按下态；按下反馈由内部控件承担"),
      selected: gated(
        "面板选中态当前由页面级 ring 工具类表达，共享层未建立统一选中契约",
      ),
      disabled: notApplicable(
        "面板本身不承载禁用语义，禁用作用于面板内部控件",
      ),
      loading: gated(
        "面板加载态由内部 LoadingSpinner 承担，共享层未建立统一加载契约",
      ),
      empty: notApplicable("面板空态由 EmptyState 组件承担"),
      error: gated(
        "面板错误态当前由页面级错误块承担，共享层未建立统一错误契约",
      ),
      success: notApplicable("面板本身没有成功态；成功反馈由内部提示承担"),
      "no-permission": notApplicable("面板本身不承载权限语义"),
    },
  },
  {
    surface: "卡片",
    control: ".ui-tag",
    states: {
      default: implemented(".ui-tag"),
      hover: notApplicable("标签不可交互，没有 hover 语义"),
      "focus-visible": notApplicable("标签不可交互，不进入焦点序列"),
      active: notApplicable("标签不可交互，没有按下语义"),
      selected: gated("标签选中态未建立共享契约"),
      disabled: notApplicable("标签没有禁用语义"),
      loading: notApplicable("标签没有加载语义"),
      empty: notApplicable("标签是静态标记，没有空态；空态由 EmptyState 承担"),
      error: gated(
        "共享层只有 blue / green / amber / purple 四种标签配色，没有错误标签语义",
      ),
      success: implemented(".ui-tag-green"),
      "no-permission": notApplicable("标签没有权限语义"),
    },
  },
  {
    surface: "表格",
    control: "（共享层尚未建立 .ui-table 契约）",
    states: {
      default: gated(
        "TableRenderer 仍使用页面级 utility；本切片不新建平行类体系，表格契约由后续页面切片收敛",
      ),
      hover: gated("表格行 hover 契约尚未建立"),
      "focus-visible": gated("表格可聚焦单元格契约尚未建立"),
      active: gated("表格排序/激活态契约尚未建立"),
      selected: gated("表格行选中态契约尚未建立"),
      disabled: gated("表格禁用行契约尚未建立"),
      loading: gated("表格加载态契约尚未建立"),
      empty: gated("表格空态契约尚未建立"),
      error: gated("表格错误态契约尚未建立"),
      success: gated("表格成功态契约尚未建立"),
      "no-permission": gated("表格无权限态契约尚未建立"),
    },
  },
  {
    surface: "菜单",
    control: "（共享层尚未建立 .ui-menu 契约）",
    states: {
      default: gated(
        "菜单当前为页面级实现，共享层没有菜单类；本切片不新建平行类体系",
      ),
      hover: gated("菜单项 hover 契约尚未建立"),
      "focus-visible": gated("菜单项焦点环契约尚未建立"),
      active: gated("菜单项按下态契约尚未建立"),
      selected: gated("菜单项选中态契约尚未建立"),
      disabled: gated("菜单项禁用态契约尚未建立"),
      loading: gated("菜单加载态契约尚未建立"),
      empty: gated("菜单空态契约尚未建立"),
      error: gated("菜单错误态契约尚未建立"),
      success: gated("菜单成功态契约尚未建立"),
      "no-permission": gated("菜单项无权限态契约尚未建立"),
    },
  },
  {
    surface: "确认弹窗",
    control: ".ui-dialog / .ui-dialog-overlay",
    states: {
      default: implemented(".ui-dialog"),
      hover: notApplicable("弹窗本体不响应 hover"),
      "focus-visible": gated(
        "弹窗容器本身不可聚焦，焦点环由内部控件承担；弹窗级焦点陷阱契约尚未建立",
      ),
      active: notApplicable("弹窗本体没有按下态"),
      selected: notApplicable("弹窗是模态容器，没有选中态；选中语义由内部控件承担"),
      disabled: notApplicable("弹窗禁用语义作用于内部按钮"),
      loading: gated(
        "弹窗提交中状态当前由按钮 disabled 表达，共享层未建立统一加载契约",
      ),
      empty: notApplicable("弹窗是模态容器，没有空态；空态由内部内容承担"),
      error: gated("弹窗错误提示当前由页面级文本承担，共享层未建立统一错误契约"),
      success: notApplicable("弹窗是模态容器，没有成功态；成功反馈由内部提示承担"),
      "no-permission": gated("弹窗无权限态契约尚未建立"),
    },
  },
];

/** 契约矩阵覆盖的全部「面 × 控件」条目。 */
export function contractEntries(): {
  surface: SharedLayerSurface;
  control: string;
  state: SharedLayerState;
  support: StateSupport;
}[] {
  return SHARED_LAYER_CONTRACT.flatMap((row) =>
    SHARED_LAYER_STATES.map((state) => ({
      surface: row.surface,
      control: row.control,
      state,
      support: row.states[state],
    })),
  );
}
