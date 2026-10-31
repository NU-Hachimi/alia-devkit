/* Tests for sdk/include/alia/save.h (make -C sdk/save test). With arguments it is a
 * small tool the Python tests use to check that both sides read each other's files:
 *   test_save write DIR NAME TEXT | read DIR NAME */
#define _POSIX_C_SOURCE 200809L
#include "alia/save.h"

#include <stdio.h>

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static long long rd(const char* name, char* buf, size_t cap) {
    long long n = alia_save_read(name, buf, cap - 1);
    if (n >= 0) buf[n] = 0;
    return n;
}

int main(int argc, char** argv) {
    if (argc == 5 && strcmp(argv[1], "write") == 0) {
        alia_save_set_dir(argv[2]);
        return alia_save_write(argv[3], argv[4], strlen(argv[4])) ? 1 : 0;
    }
    if (argc == 4 && strcmp(argv[1], "read") == 0) {
        char buf[4096];
        alia_save_set_dir(argv[2]);
        if (rd(argv[3], buf, sizeof buf) < 0) return 1;
        fputs(buf, stdout);
        return 0;
    }

    char dir[] = "/tmp/alia-save-test-XXXXXX";
    CHECK(mkdtemp(dir));
    alia_save_set_dir(dir);
    char buf[256];

    CHECK(rd("slot1", buf, sizeof buf) == -ENOENT);
    CHECK(alia_save_write("slot1", "one", 3) == 0);
    CHECK(alia_save_write("slot1", "two", 3) == 0);
    CHECK(alia_save_write("slot1", "three", 5) == 0);
    CHECK(alia_save_write("slot1", "four", 4) == 0);  /* "one" falls off */
    CHECK(rd("slot1", buf, sizeof buf) == 4 && strcmp(buf, "four") == 0);
    CHECK(alia_save_read_version("slot1", 2, buf, sizeof buf) == 3 && memcmp(buf, "two", 3) == 0);
    CHECK(alia_save_size("slot1") == 4);
    CHECK(alia_save_read("slot1", buf, 2) == -EMSGSIZE);

    /* current lost (crash between the renames): the newest older version is read */
    char p[4200];
    snprintf(p, sizeof p, "%s/slot1", dir);
    unlink(p);
    CHECK(rd("slot1", buf, sizeof buf) == 5 && strcmp(buf, "three") == 0);

    CHECK(alia_save_rollback("slot1", 1) == 0);  /* "three" current again */
    CHECK(rd("slot1", buf, sizeof buf) == 5 && strcmp(buf, "three") == 0);

    CHECK(alia_save_write("bad/name", "x", 1) == -EINVAL);
    CHECK(alia_save_write(".hidden", "x", 1) == -EINVAL);
    CHECK(alia_save_write("x.tmp", "x", 1) == -EINVAL);

    CHECK(alia_save_write("b-slot", "b", 1) == 0);
    char names[4][ALIA_SAVE_NAME_MAX + 1];
    CHECK(alia_save_list(names, 4) == 2 && strcmp(names[0], "b-slot") == 0 && strcmp(names[1], "slot1") == 0);

    setenv("ALIA_SAVE_QUOTA_KB", "1", 1);
    static char big[2048];
    CHECK(alia_save_write("big", big, sizeof big) == -ENOSPC);
    CHECK(alia_save_write("small", big, 100) == 0);
    unsetenv("ALIA_SAVE_QUOTA_KB");

    CHECK(alia_save_delete("slot1") == 0);
    CHECK(rd("slot1", buf, sizeof buf) == -ENOENT);
    alia_save_delete("b-slot");
    alia_save_delete("small");
    CHECK(rmdir(dir) == 0);  /* nothing left behind, not even temp files */

    printf(failures ? "%d failures\n" : "ok (0 failures)\n", failures);
    return failures != 0;
}
