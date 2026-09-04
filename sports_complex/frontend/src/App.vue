<template>
  <!-- Fullscreen app shell: h-screen + overflow-hidden here means the
       browser's own window never scrolls (see www/portal/index.html's
       matching html/body overflow:hidden) - only the <main> region below
       scrolls, if a page's content is taller than the viewport (e.g.
       BookFacility's calendar+cart). Navbar sits outside that scrolling
       area so it never needs "sticky" positioning - it structurally can't
       scroll out of view. -->
  <div class="flex h-screen flex-col overflow-hidden bg-slate-50">
    <Navbar />
    <main class="min-h-0 flex-1 overflow-y-auto">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import Navbar from '@/components/Navbar.vue';
</script>
