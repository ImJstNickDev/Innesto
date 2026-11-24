#include "runtime.h"
#include "runtime_adapter.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expression) do { \
    if (!(expression)) { \
        fprintf(stderr, "contract failed at line %d: %s\n", __LINE__, #expression); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

static const struct innesto_mod_context client_context = { "client-example", INNESTO_PHYSICAL_CLIENT };
static const struct innesto_mod_context server_context = { "server-example", INNESTO_PHYSICAL_SERVER };
static const struct innesto_common_v1 *common;
static int callbacks_completed;

static void count_callback(const struct innesto_mod_context *context, void *data)
{
    int *expected = data;
    CHECK(common->logical_side() == INNESTO_LOGICAL_UNKNOWN);
    CHECK(context == (*expected < 2 ? &client_context : &server_context));
    CHECK(common->on_startup_complete(context, count_callback, data) == INNESTO_STARTUP_CLOSED);
    CHECK(callbacks_completed++ == *expected);
}

static int initialize(const struct innesto_mod_context *context)
{
    static int order[] = { 0, 1, 2 };
    CHECK(callbacks_completed == 0);
    CHECK(common->logical_side() == INNESTO_LOGICAL_UNKNOWN);
    CHECK(common->on_startup_complete(context, NULL, NULL) == INNESTO_STARTUP_INVALID);
    if (context == &client_context) {
        CHECK(common->on_startup_complete(&server_context, count_callback, order) == INNESTO_STARTUP_CLOSED);
        CHECK(common->on_startup_complete(context, count_callback, &order[0]) == INNESTO_STARTUP_REGISTERED);
        CHECK(common->on_startup_complete(context, count_callback, &order[1]) == INNESTO_STARTUP_REGISTERED);
    } else {
        CHECK(common->on_startup_complete(context, count_callback, &order[2]) == INNESTO_STARTUP_REGISTERED);
    }
    return 0;
}

static void check_client_scope(void *data)
{
    CHECK(common->logical_side() == INNESTO_LOGICAL_CLIENT);
    CHECK(data == &callbacks_completed);
}

static void *check_worker_scope(void *data)
{
    CHECK(common->logical_side() == INNESTO_LOGICAL_UNKNOWN);
    CHECK(innesto_adapter_dispatch_v1(INNESTO_LOGICAL_CLIENT, check_client_scope, data));
    CHECK(common->logical_side() == INNESTO_LOGICAL_UNKNOWN);
    return NULL;
}

static void check_integrated_simulation(void *data)
{
    CHECK(common->physical_environment(&client_context) == INNESTO_PHYSICAL_CLIENT);
    CHECK(common->logical_side() == INNESTO_LOGICAL_SERVER);
    CHECK(innesto_adapter_dispatch_v1(INNESTO_LOGICAL_CLIENT, check_client_scope, data));
    CHECK(common->logical_side() == INNESTO_LOGICAL_SERVER);
    pthread_t worker;
    CHECK(pthread_create(&worker, NULL, check_worker_scope, data) == 0);
    CHECK(pthread_join(worker, NULL) == 0);
    CHECK(common->logical_side() == INNESTO_LOGICAL_SERVER);
}

int main(void)
{
    /* The fixture publishes an original table on one physical environment. */
    static const int fixture_table = 123;
    const char *fixture_name = "fixture.attached";
    CHECK(innesto_adapter_provide_v1(INNESTO_PHYSICAL_CLIENT, fixture_name, 1, &fixture_table));
    CHECK(!innesto_adapter_provide_v1(INNESTO_PHYSICAL_CLIENT, fixture_name, 1, &fixture_table));
    CHECK(!innesto_adapter_provide_v1(INNESTO_PHYSICAL_CLIENT, INNESTO_CAP_SERVER, 1, &fixture_table));
    CHECK(!innesto_adapter_provide_v1(0, fixture_name, 1, &fixture_table));
    CHECK(!innesto_adapter_provide_v1(INNESTO_PHYSICAL_SERVER, fixture_name, 1, NULL));
    innesto_seal_capabilities();
    CHECK(!innesto_adapter_provide_v1(INNESTO_PHYSICAL_SERVER, fixture_name, 1, &fixture_table));
    CHECK(innesto_query_capability_v1(&client_context, fixture_name, 1) == &fixture_table);
    CHECK(!innesto_query_capability_v1(&client_context, fixture_name, 2));
    CHECK(!innesto_query_capability_v1(&server_context, fixture_name, 1));
    CHECK(!innesto_query_capability_v1(&client_context, "fixture.missing", 1));
    CHECK(!innesto_query_capability_v1(NULL, INNESTO_CAP_COMMON, 1));
    CHECK(!innesto_query_capability_v1(&client_context, NULL, 1));
    CHECK(!innesto_query_capability_v1(&client_context, INNESTO_CAP_COMMON, 2));
    common = innesto_query_capability_v1(&client_context, INNESTO_CAP_COMMON, 1);
    CHECK(common && innesto_query_capability_v1(&server_context, INNESTO_CAP_COMMON, 1) == common);
    CHECK(strcmp(common->mod_id(&client_context), "client-example") == 0);
    CHECK(!innesto_query_capability_v1(&client_context, INNESTO_CAP_SERVER, 1));
    CHECK(!innesto_query_capability_v1(&server_context, INNESTO_CAP_CLIENT, 1));
    CHECK(!innesto_adapter_dispatch_v1(INNESTO_LOGICAL_SERVER, check_integrated_simulation, NULL));
    CHECK(innesto_initialize_v2(&client_context, initialize) == 0);
    CHECK(innesto_initialize_v2(&server_context, initialize) == 0);
    innesto_finish_startup();
    CHECK(callbacks_completed == 3);
    CHECK(!innesto_adapter_dispatch_v1(INNESTO_LOGICAL_UNKNOWN, check_client_scope, NULL));
    CHECK(!innesto_adapter_dispatch_v1(INNESTO_LOGICAL_SERVER, NULL, NULL));
    CHECK(innesto_adapter_dispatch_v1(INNESTO_LOGICAL_SERVER, check_integrated_simulation, &callbacks_completed));
    CHECK(common->logical_side() == INNESTO_LOGICAL_UNKNOWN);
    return 0;
}
