:original_name: merge_demo.html

.. _merge_demo:

Creating a Thing
================

Function
--------

Some request bodies are split across two tables; both must merge into the
single ``body`` section (exercises _merge_table_into_section).

URI
---

POST /v1/{project_id}/things

Request
-------

.. table:: **Table 1** Request body parameters

   ========= ========= ====== ===========
   Parameter Mandatory Type   Description
   ========= ========= ====== ===========
   name      Yes       String The name.
   ========= ========= ====== ===========

.. table:: **Table 2** Request body parameters

   ========= ========= ======= ===========
   Parameter Mandatory Type    Description
   ========= ========= ======= ===========
   age       No        Integer The age.
   ========= ========= ======= ===========
