<template>
  <div class="p-6">
    <PageHeader
      title="企业 360 背调"
      subtitle="创建背调任务、锚定企业主体、运行内外数据整合背调并查看企业画像报告"
    >
      <template #extra>
        <button
          class="ui-btn ui-btn-primary"
          data-testid="create-task-btn"
          @click="openCreate"
        >
          <Plus :size="16" /> 新建背调任务
        </button>
      </template>
    </PageHeader>

    <div class="mt-4">
      <LoadingSpinner v-if="loading" text="加载背调任务..." />
      <EmptyState
        v-else-if="tasks.length === 0"
        title="暂无背调任务"
        hint="点击右上角「新建背调任务」开始一次企业 360 背调"
      />
      <div v-else class="dd-table">
        <div class="dd-header">
          <div class="col-title">任务</div>
          <div class="col-subject">主体</div>
          <div class="col-status">状态</div>
          <div class="col-ops">操作</div>
        </div>
        <div
          v-for="task in tasks"
          :key="task.id"
          class="dd-row"
          data-testid="task-row"
        >
          <div class="col-title">
            <span class="row-title">{{ task.title }}</span>
            <span class="row-query" :title="task.subject_query">{{ task.subject_query }}</span>
          </div>
          <div class="col-subject">
            <span v-if="task.confirmed_subject" class="row-subject" data-testid="task-subject">
              {{ task.confirmed_subject.company_name }}
            </span>
            <span v-else class="text-[var(--color-ink-tertiary)] text-[var(--text-small)]">未确认</span>
          </div>
          <div class="col-status">
            <span class="ui-tag" :class="taskStatus(task.status).tag" data-testid="task-status">
              {{ taskStatus(task.status).label }}
            </span>
          </div>
          <div class="col-ops">
            <button
              class="ui-btn ui-btn-ghost"
              data-testid="open-task-btn"
              @click="goDetail(task.id)"
            >
              进入
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-mask" data-testid="create-modal" @click.self="closeCreate">
        <div class="modal-panel">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-3">新建背调任务</h3>
          <div class="form-col">
            <label class="form-field">
              <span class="form-label">任务标题 <span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.title"
                class="ui-input"
                data-testid="input-title"
                placeholder="如 某科技公司入驻背调"
              />
            </label>
            <label class="form-field">
              <span class="form-label">主体查询（企业名称 / 关键词）<span class="text-[var(--color-danger)]">*</span></span>
              <input
                v-model="form.subject_query"
                class="ui-input"
                data-testid="input-subject-query"
                placeholder="如 某某科技有限公司"
              />
              <span class="form-hint">
                提交后先锚定企业主体（外部工商核验），人工确认后再运行背调。
              </span>
            </label>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button class="ui-btn ui-btn-ghost" data-testid="cancel-create" @click="closeCreate">取消</button>
            <button
              class="ui-btn ui-btn-primary"
              data-testid="submit-create"
              :disabled="creating || !form.title.trim() || !form.subject_query.trim()"
              @click="submitCreate"
            >
              {{ creating ? "创建中..." : "创建任务" }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Plus } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { useToast } from "@/composables/useToast";
import { listTasks, createTask, type DdTask } from "@/services/dueDiligence";
import { taskStatus } from "./status";

const router = useRouter();
const toast = useToast();

const tasks = ref<DdTask[]>([]);
const loading = ref(false);

const showCreate = ref(false);
const creating = ref(false);
const form = reactive({ title: "", subject_query: "" });

function openCreate() {
  form.title = "";
  form.subject_query = "";
  showCreate.value = true;
}
function closeCreate() {
  showCreate.value = false;
}

function goDetail(id: string) {
  router.push({ name: "AppEnterprise360DdDetail", params: { id } });
}

interface AxiosLikeError {
  response?: { status?: number; data?: { detail?: string } };
}
function errorDetail(e: unknown, fallback: string): string {
  return (e as AxiosLikeError).response?.data?.detail ?? fallback;
}

async function submitCreate() {
  if (!form.title.trim() || !form.subject_query.trim()) {
    toast.error("请填写任务标题与主体查询");
    return;
  }
  creating.value = true;
  try {
    const task = await createTask({
      title: form.title.trim(),
      subject_query: form.subject_query.trim(),
    });
    toast.success("已创建，去锚定主体");
    showCreate.value = false;
    goDetail(task.id);
  } catch (e) {
    toast.error(errorDetail(e, "创建失败"));
  } finally {
    creating.value = false;
  }
}

async function load() {
  loading.value = true;
  try {
    tasks.value = await listTasks();
  } catch (e) {
    toast.error(errorDetail(e, "加载背调任务失败"));
    tasks.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.dd-table {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.06);
}
.dd-header,
.dd-row {
  display: grid;
  grid-template-columns: 1.6fr 1.4fr 130px 90px;
  gap: 0;
  padding: 10px 16px;
  align-items: center;
}
.dd-header {
  background: #f8f9fa;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  border-bottom: 1px solid #e5e7eb;
}
.dd-row {
  border-bottom: 1px solid #f3f4f6;
}
.dd-row:last-child {
  border-bottom: none;
}
.dd-row:hover {
  background: #f9fafb;
}
.col-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.row-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink);
}
.row-query {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-subject {
  font-size: 13px;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: white;
  border-radius: 12px;
  padding: 20px 24px;
  width: 100%;
  max-width: 460px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
}
.form-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-label {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  font-weight: 500;
}
.form-hint {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  line-height: 1.5;
}

.ui-tag-blue {
  display: inline-flex;
  align-items: center;
  background: #eef2ff;
  color: #4338ca;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-amber {
  display: inline-flex;
  align-items: center;
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-green {
  display: inline-flex;
  align-items: center;
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-red {
  display: inline-flex;
  align-items: center;
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
.ui-tag-grey {
  display: inline-flex;
  align-items: center;
  background: #e5e7eb;
  color: #6b7280;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
</style>
