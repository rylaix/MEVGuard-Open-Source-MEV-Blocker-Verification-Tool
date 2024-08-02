// c_extension/c_extension.c

#include <Python.h>

// Example function: Add two numbers
static PyObject* add(PyObject* self, PyObject* args) {
    double a, b;
    if (!PyArg_ParseTuple(args, "dd", &a, &b))
        return NULL;
    return Py_BuildValue("d", a + b);
}

// Method definitions
static PyMethodDef methods[] = {
    {"add", add, METH_VARARGS, "Add two numbers"},
    {NULL, NULL, 0, NULL}
};

// Module definition
static struct PyModuleDef c_extension_module = {
    PyModuleDef_HEAD_INIT,
    "c_extension",
    "Example C extension module",
    -1,
    methods
};

// Module initialization
PyMODINIT_FUNC PyInit_c_extension(void) {
    return PyModule_Create(&c_extension_module);
}
