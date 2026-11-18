:original_name: en-us_topic_0000001487936070.html

.. _en-us_topic_0000001487936070:

What Are the Relationships Among Firewall Groups, Policies, and Rules?
======================================================================

Relationships
-------------

Firewall resources are classified into groups, policies, and rules.

The relationships among them are as follows:

-  A firewall policy can be associated with multiple firewall rules.
-  A firewall group can be associated with two firewall policies. One policy controls inbound traffic and the other controls outbound traffic.
-  A firewall policy must be associated with a firewall group.

Log in to the network console and view basic information about the firewall. You can view the name and ID of the firewall.

|image1|

On the **Inbound Rules** or **Outbound Rules** tab, you can add, modify, or delete firewall rules. These rules are associated with the same inbound or outbound policy.

|image2|

Example
-------

The following describes how to create firewall resources.

-  Creating a firewall rule

.. code-block:: text

   POST /v2.0/fwaas/firewall_rules

Request body

.. code-block::

   {
       "firewall_rule": {
           "name": "fw-rule-ingress-1",
           "description": "create a ingress firewall rule ",
           "protocol": "TCP",
           "action": "ALLOW",
           "ip_version": 4,
           "destination_ip_address": "192.168.22.0/24",
           "source_ip_address": "0.0.0.0/0",
           "enabled": true
       }
   }

Response body of obtaining **firewall_rule_id**: 84d10f4a-9f8b-41b8-bdfa-5a0f18736f12

.. code-block::

   {
       "firewall_rule": {
           "protocol": "tcp",
           "description": "create a ingress firewall rule ",
           "source_ip_address": "0.0.0.0/0",
           "destination_ip_address": "192.168.22.0/24",
           "source_port": null,
           "destination_port": null,
           "id": "84d10f4a-9f8b-41b8-bdfa-5a0f18736f12",
           "name": "fw-rule-ingress-1",
           "tenant_id": "5f6387106c2048b589b369d96c2f23a2",
           "project_id": "5f6387106c2048b589b369d96c2f23a2",
           "enabled": true,
           "action": "allow",
           "ip_version": 4,
           "public": false
       }
   }

-  Creating a firewall policy

.. code-block:: text

   POST /v2.0/fwaas/firewall_policies

Request body of associating with a firewall rule

.. code-block::

   {
       "firewall_policy": {
           "description": "create a ingress firewall policy",
           "firewall_rules": [
             "84d10f4a-9f8b-41b8-bdfa-5a0f18736f12"
           ],
           "name": "fw-policy-ingress"
       }
   }

Response body of obtaining **firewall_policy_id**: da037721-b895-4e07-bbcc-f5f6ac2759fb

.. code-block::

   {
       "firewall_policy": {
           "id": "da037721-b895-4e07-bbcc-f5f6ac2759fb",
           "name": "fw-policy-ingress",
           "project_id": "5f6387106c2048b589b369d96c2f23a2",
           "tenant_id": "5f6387106c2048b589b369d96c2f23a2",
           "description": "create a ingress firewall policy",
           "firewall_rules": [
             "84d10f4a-9f8b-41b8-bdfa-5a0f18736f12"
           ],
           "audited": false,
           "public": false
       }
   }

-  Creating a firewall group

.. code-block:: text

   POST /v2.0/fwaas/firewall_groups

Request body of associating with an inbound firewall policy

.. code-block::

   {
       "firewall_group": {
           "name": "fw-group-example",
           "description": "create a firewall group",
           "ingress_firewall_policy_id": "da037721-b895-4e07-bbcc-f5f6ac2759fb",
           "admin_state_up": true
       }
   }

Response body of obtaining **firewall_group_id**: 102493e8-fc6d-4f0d-b57f-55c5be86f5c0.

.. code-block::

   {
       "firewall_group": {
           "id": "102493e8-fc6d-4f0d-b57f-55c5be86f5c0",
           "name": "fw-group-example",
           "project_id": "5f6387106c2048b589b369d96c2f23a2",
           "tenant_id": "5f6387106c2048b589b369d96c2f23a2",
           "admin_state_up": true,
           "egress_firewall_policy_id": null,
           "ingress_firewall_policy_id": "da037721-b895-4e07-bbcc-f5f6ac2759fb",
           "description": "create a firewall group",
           "created_at": "2023-03-09T08:54:40",
           "updated_at": "2023-03-09T08:54:40",
           "status": "INACTIVE",
           "ports": [],
           "public": false
       }
   }

Log in to the network console and view the created firewall resources.

|image3|

.. |image1| image:: /_static/images/en-us_image_0000001487964866.png
.. |image2| image:: /_static/images/en-us_image_0000001538445357.png
.. |image3| image:: /_static/images/en-us_image_0000001538444809.png
