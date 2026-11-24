/* Optional, self-contained evaluation against the pinned Linux x86-64 devkit. */
#include <frida-gum.h>
#include <stdio.h>
#include <string.h>

static unsigned originals;

__attribute__((noinline)) static int owned_break_rule(int present)
{
    originals++;
    return present ? 7 : 0;
}

static void count_entry(GumInvocationContext *invocation, gpointer data)
{
    (void)invocation;
    ++*(unsigned *)data;
}

int main(void)
{
    unsigned entries = 0;
    int (*const rule)(int) = owned_break_rule;
    gpointer owned_function;
    _Static_assert(sizeof(rule) == sizeof(owned_function), "Linux x86-64 pointer size");
    memcpy(&owned_function, &rule, sizeof(rule));

    gum_init_embedded();
    GumModule *self = gum_process_get_main_module();
    GumInterceptor *interceptor = gum_interceptor_obtain();
    GumInvocationListener *listener = gum_make_call_listener(count_entry, NULL, &entries, NULL);
    int hidden = gum_module_find_export_by_name(self, "owned_break_rule") == 0;
    GumAttachReturn attached =
        gum_interceptor_attach(interceptor, owned_function, listener, NULL, GUM_ATTACH_FLAGS_NONE);
    int allowed = owned_break_rule(1);
    int denied = owned_break_rule(0);
    gum_interceptor_detach(interceptor, listener);
    int after = owned_break_rule(1);
    printf("hidden=%d attached=%d entries=%u originals=%u results=%d,%d,%d\n",
        hidden,
        attached == GUM_ATTACH_OK,
        entries,
        originals,
        allowed,
        denied,
        after);
    int ok = hidden && attached == GUM_ATTACH_OK && entries == 2 && originals == 3 && allowed == 7 &&
             denied == 0 && after == 7;
    g_object_unref(listener);
    g_object_unref(interceptor);
    gum_deinit_embedded();
    return ok ? 0 : 1;
}
