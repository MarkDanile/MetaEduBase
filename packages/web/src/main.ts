import { createApp } from "vue";
import { createPinia } from "pinia";
import { QueryCache, QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import App from "./app/App.vue";
import router from "./app/router";
import { useThemeStore } from "@/stores/theme";
import { useToast } from "@/composables/useToast";
import "@/assets/css/main.css";

const app = createApp(App);

app.use(createPinia());
app.use(router);

const toast = useToast();
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      const message =
        error instanceof Error ? error.message : "请求失败";
      toast.error(message);
    },
  }),
});
app.use(VueQueryPlugin, { queryClient });

useThemeStore();

app.mount("#app");
