import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin } from "@tanstack/vue-query";
import App from "./app/App.vue";
import router from "./app/router";
import { useThemeStore } from "@/stores/theme";
import "@/assets/css/main.css";

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(VueQueryPlugin);

useThemeStore();

app.mount("#app");
