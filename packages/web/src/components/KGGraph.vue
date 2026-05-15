<template>
  <div ref="containerRef" class="w-full rounded-lg overflow-hidden" :style="{ height: `${height}px` }" />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";
import { Graph } from "@antv/g6";
import type { NodeData, EdgeData } from "@antv/g6";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";

export interface KGGraphProps {
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
  height?: number;
}

const props = withDefaults(defineProps<KGGraphProps>(), { height: 500 });

const emit = defineEmits<{
  "node-click": [node: KnowledgeNodeDTO];
}>();

const containerRef = ref<HTMLDivElement | null>(null);
let graph: Graph | null = null;

const DOMAIN_COLORS: Record<string, string> = {
  electronics_info: "#3b82f6",
  smart_manufacturing: "#8b5cf6",
  finance_commerce: "#f59e0b",
  medical_health: "#ef4444",
  education_sports: "#10b981",
  civil_engineering: "#6366f1",
  transportation: "#14b8a6",
  agriculture: "#84cc16",
  art_design: "#ec4899",
  public_service: "#64748b",
};

const LEVEL_SIZES: Record<string, number> = {
  professional: 60,
  course: 50,
  chapter: 44,
  knowledge_point: 36,
  skill_point: 36,
  operation_step: 28,
};

function colorByDomain(domain: string): string {
  return DOMAIN_COLORS[domain] ?? "#94a3b8";
}

function sizeByLevel(level: string): number {
  return LEVEL_SIZES[level] ?? 36;
}

function buildGraphData() {
  return {
    nodes: props.nodes.map((n) => ({
      id: n.id,
      data: { ...n },
      style: {
        size: sizeByLevel(n.level),
        color: colorByDomain(n.domain),
        labelText: n.title,
      },
    })),
    edges: props.edges.map((e) => ({
      id: e.id,
      source: e.source_id,
      target: e.target_id,
      data: { relation: e.relation_type },
      style: {
        labelText: e.relation_type,
        endArrow: true,
      },
    })),
  };
}

onMounted(() => {
  if (!containerRef.value) return;

  graph = new Graph({
    container: containerRef.value,
    width: containerRef.value.clientWidth,
    height: props.height,
    data: buildGraphData(),
    behaviors: [
      "drag-canvas",
      "zoom-canvas",
      { type: "click-select", items: ["node"] },
    ],
    node: {
      style: {
        size: (d: NodeData) => {
          const nd = d.data as unknown as KnowledgeNodeDTO;
          return sizeByLevel(nd?.level ?? "knowledge_point");
        },
        fill: (d: NodeData) => {
          const nd = d.data as unknown as KnowledgeNodeDTO;
          return colorByDomain(nd?.domain ?? "education_sports");
        },
        stroke: (d: NodeData) => {
          const nd = d.data as unknown as KnowledgeNodeDTO;
          return colorByDomain(nd?.domain ?? "education_sports") + "40";
        },
        lineWidth: 1,
        labelText: (d: NodeData) => {
          const nd = d.data as unknown as KnowledgeNodeDTO;
          return nd?.title ?? "";
        },
        labelFill: "#1e293b",
        labelFontSize: 11,
        labelOffsetY: 2,
        labelMaxWidth: 80,
        labelWordWrap: true,
        radius: 4,
      },
    },
    edge: {
      style: {
        stroke: "#cbd5e1",
        lineWidth: 1,
        labelText: (d: EdgeData) => {
          const ed = d.data as unknown as { relation: string };
          return ed?.relation ?? "";
        },
        labelFill: "#64748b",
        labelFontSize: 10,
        labelBackground: true,
        labelBackgroundRadius: 2,
        labelBackgroundPadding: [2, 4],
        labelBackgroundFill: "#f8fafc",
        endArrow: true,
        endArrowSize: 4,
        endArrowFill: "#cbd5e1",
        router: false,
      },
    },
    layout: {
      type: "force",
      preventOverlap: true,
      nodeSpacing: 24,
      edgeSpacing: 12,
      iterations: 200,
      alpha: 0.3,
      alphaDecay: 0.03,
    },
    plugins: [
      {
        type: "tooltip",
        getContent: (e: { target: { id: () => string } }) => {
          const node = props.nodes.find((n) => n.id === e.target.id());
          if (!node) return "";
          return `<div style="padding:4px">
            <b>${node.title}</b><br/>
            <span style="color:#64748b;font-size:10px">${node.domain} / ${node.level}</span>
          </div>`;
        },
      },
    ],
    autoFit: "view",
    padding: [24, 24, 24, 24],
  });

  graph.on("node:click", (e: any) => {
    const node = props.nodes.find((n) => n.id === e.id);
    if (node) emit("node-click", node);
  });

  graph.render();
});

onUnmounted(() => {
  graph?.destroy();
  graph = null;
});

watch(
  () => [props.nodes, props.edges],
  () => {
    if (!graph) return;
    graph.setData(buildGraphData());
    graph.render();
  },
  { deep: true }
);
</script>
