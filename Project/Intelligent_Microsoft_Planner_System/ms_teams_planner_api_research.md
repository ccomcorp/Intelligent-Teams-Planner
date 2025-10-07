# Research Report: Microsoft Graph API and Teams Planner Capabilities for Natural Language Interface Development

**Report Date:** 2025-10-06

**Objective:** This report provides a comprehensive analysis of the Microsoft Graph API's capabilities for interacting with Microsoft Planner. The research covers the full spectrum of Planner API functionalities, authentication protocols, operational endpoints, performance considerations, and best practices. The primary objective is to equip technical developers with the necessary knowledge to build a sophisticated natural language interface system integrated with Microsoft Planner, such as for an MCP/OpenWebUI platform.

### Executive Summary

The Microsoft Graph API offers a robust and extensive set of tools for programmatic interaction with Microsoft Planner, making it a highly viable foundation for developing a natural language interface. The API exposes a comprehensive data model that includes plans, buckets, tasks, and associated details like assignments, checklists, and attachments, all manageable through standard CRUD (Create, Read, Update, Delete) operations. Authentication is securely handled via the Microsoft identity platform using standard OAuth 2.0 flows, with granular permission scopes ensuring adherence to the principle of least privilege.

Key strengths of the API for this purpose include its support for batch operations, which allows for the efficient execution of multiple commands derived from a single natural language query, and its detailed data model that enables precise manipulation of Planner entities. However, developers must navigate several critical considerations. The API is subject to stringent rate limits and throttling policies, necessitating the implementation of sophisticated error handling, query optimization, and backoff strategies. Furthermore, while the Graph API provides a powerful change notification framework via webhooks for many Microsoft 365 services, Planner resources are not explicitly listed as a supported source for real-time notifications. This limitation requires developers to implement alternative synchronization strategies, such as periodic polling or the use of delta queries, which may introduce latency. Finally, the API currently provides access only to basic Planner features, with premium functionalities remaining inaccessible.

This report concludes that while the Microsoft Graph API for Planner is a powerful platform for building a natural language-driven task management system, a successful implementation requires careful architectural design to manage its limitations, particularly concerning real-time data synchronization and service throttling.

---

## 1.0 Authentication and Authorization Framework

Secure and authorized access to Microsoft Planner data via the Graph API is governed by the Microsoft identity platform, which utilizes the OAuth 2.0 protocol. This framework ensures that any application, including a natural language interface, can only access data for which it has been explicitly granted permission by either a user or a tenant administrator. Understanding these authentication flows and permission scopes is fundamental for developers building integrations.

### 1.1 OAuth 2.0 Authentication Flows

The Microsoft identity platform supports several OAuth 2.0 authentication flows, each tailored to different application architectures and scenarios. For a system designed to interact with Planner, the choice of flow depends on whether the application will act on behalf of a signed-in user (delegated access) or operate autonomously as a background service (app-only access).

The **Authorization Code Flow** is the recommended and most secure method for applications where a user is present and can interactively sign in, such as a web application. In this flow, the application redirects the user to the Microsoft identity platform's authorization endpoint to sign in and consent to the requested permissions. Upon successful authentication, the platform returns an authorization code to the application. The application then securely exchanges this code for an access token and a refresh token at the token endpoint. The access token is presented in the `Authorization` header of subsequent API calls to Microsoft Graph. This flow is ideal for a natural language interface where actions are performed in the context of the logged-in user.

The **Client Credentials Flow** is designed for non-interactive scenarios, such as background services or daemons that need to perform actions without a signed-in user. In this model, the application authenticates using its own identity—a client ID and a client secret or certificate—to obtain an access token directly from the token endpoint. This flow is suitable for system-level integrations, such as an automated process that generates Planner tasks from another system. Permissions granted in this flow are application permissions, which are typically more privileged and always require consent from a tenant administrator.

The **On-Behalf-Of Flow** is a more complex scenario applicable when a middle-tier service needs to call another API, like Microsoft Graph, on behalf of a user who has authenticated to the front-end application. The middle-tier service exchanges the user's initial access token for a new one with the appropriate scopes to call the downstream API. While less common for a direct Planner integration, it is a relevant pattern in multi-service architectures.

Historically, the **Implicit Grant Flow** was used for single-page applications (SPAs), but it is no longer recommended due to security vulnerabilities. Modern applications should use the Authorization Code Flow with Proof Key for Code Exchange (PKCE) for enhanced security.

### 1.2 Planner Permission Scopes

Access to Planner resources is controlled by specific permission scopes that an application must request and receive consent for. These scopes define the level of access the application has and are categorized as either delegated or application permissions.

**Delegated Permissions** are used when an application acts on behalf of a signed-in user. The effective permissions are the intersection of the permissions granted to the application and the privileges of the signed-in user. For Planner, the primary delegated scopes are:
*   **`Tasks.Read`**: Allows the application to read the plans and tasks that the signed-in user has access to.
*   **`Tasks.ReadWrite`**: Allows the application to read, create, update, and delete plans and tasks that the signed-in user has access to. This is the essential scope for a natural language interface that needs to perform actions like creating or modifying tasks.

**Application Permissions** are used for app-only access without a signed-in user. These permissions grant the application broad access across the organization and require administrator consent. The relevant scopes for Planner are:
*   **`Tasks.Read.All`**: Allows the application to read all plans and tasks in the organization.
*   **`Tasks.ReadWrite.All`**: Allows the application to read, create, update, and delete all plans and tasks in the organization. This scope is powerful and suitable for automation and administrative tools.

When requesting permissions, developers must adhere to the principle of least privilege, requesting only the scopes necessary for the application's functionality. For instance, an interface that only displays tasks should request `Tasks.Read`, not `Tasks.ReadWrite`. This practice enhances security and increases the likelihood of user consent.

## 2.0 The Planner API Data Model and Capabilities

The Microsoft Graph API exposes Planner through a structured and hierarchical data model. A thorough understanding of this model is crucial for translating natural language commands into precise API operations. The core entities are plans, buckets, and tasks, each with a set of detailed properties and relationships that enable rich task management functionalities.

### 2.1 Plans: The Top-Level Containers

A **plan** is the primary container for tasks in Microsoft Planner. Critically, every plan must be associated with a container resource, most commonly a Microsoft 365 group. This association dictates the plan's membership, authorization rules, and lifecycle. When a group is deleted, its associated plans are also deleted. To create a plan, an application must specify the ID of the containing group, and the user or application performing the action must have membership or permissions within that group. The API does not support the creation of standalone plans. It is also important to note that the API currently only supports basic plans; premium Planner features, such as custom fields or advanced timelines, are not accessible.

### 2.2 Buckets: Organizing Tasks

Within each plan, tasks are organized into **buckets**. Buckets function as columns on a task board, allowing users to categorize tasks by status, workstream, or any other custom classification (e.g., "To Do," "In Progress," "Completed"). Each plan can contain multiple buckets. The visual order of buckets within the Planner interface is controlled by the `orderHint` property, a string value that the API uses for sorting. When creating or updating buckets, applications must provide a correctly formatted `orderHint` string to position the bucket relative to its siblings.

### 2.3 Tasks: The Core Work Items

The **task** is the fundamental unit of work in Planner. Each task belongs to a single plan and a single bucket. The task resource is split into two objects to optimize performance: a basic task object and a task details object. The basic object contains frequently accessed properties suitable for list views, such as `title`, `dueDate`, `percentComplete`, and `priority`. The more detailed properties are stored in a separate `plannerTaskDetails` object, which must be explicitly requested using the `$expand=details` query parameter. This separation ensures that simple list queries remain lightweight and fast.

### 2.4 Task Assignments

Tasks can be assigned to one or more users who are members of the plan's parent group. Assignments are managed through the `assignments` property on the task object. This property is a collection where each entry maps a user's ID to an assignment object containing an `orderHint` property. This allows for prioritizing assignments for a given user. A single task can have a maximum of 20 assignees. A natural language command like "Assign the 'review document' task to Jane" would require the system to first resolve "Jane" to her user ID and then update the task's `assignments` collection.

### 2.5 Labels (Applied Categories)

Planner allows tasks to be categorized using colored labels. The API manages these through the `appliedCategories` property within the `plannerTaskDetails` object. This property is a collection of boolean flags (e.g., `category1`, `category2`, etc.) corresponding to the six available colored labels in the Planner UI. To apply a label to a task, the application sets the corresponding category flag to `true`. There is no dedicated API endpoint for managing the names of these labels themselves; label names are defined at the plan level and are not directly queryable as distinct entities.

### 2.6 Checklists

For tasks that involve multiple steps, Planner supports checklists. A checklist is a collection of individual items within a task that can be marked as complete. This functionality is managed via the `checklist` property of the `plannerTaskDetails` object. The property contains a collection of checklist items, each with a unique ID, a `title`, and an `isChecked` boolean property. Applications can add, update, or delete checklist items to programmatically manage sub-task progress. A plan is limited to a maximum of 50 checklist items per task.

### 2.7 Attachments and References

Attachments on a Planner task are handled as external references rather than direct file uploads to the Planner service. These are managed through the `references` property on the `plannerTaskDetails` object. Each reference is a link to an external resource, which is often a file stored in the SharePoint document library of the associated Microsoft 365 group. An application can add an attachment by creating a new reference with the URL of the resource. This design means that managing the files themselves may require separate calls to the SharePoint or OneDrive APIs.

### 2.8 Comments and Conversations

Comments on Planner tasks are not stored directly within the Planner data model. Instead, they are integrated with the conversation feature of the underlying Microsoft 365 group. While the `description` property of the `plannerTaskDetails` object can hold detailed notes, true conversational history is part of the group's Outlook conversations. To retrieve the full comment thread for a task, an application would need to use the Microsoft Graph API for Outlook Groups, linking the task to its corresponding conversation thread. This adds a layer of complexity for a natural language interface aiming to manage task comments.

## 3.0 CRUD Endpoints and Operational Logic

The Microsoft Graph API provides a comprehensive set of RESTful endpoints for performing CRUD operations on all major Planner resources. These operations are executed using standard HTTP methods: `POST` for creation, `GET` for retrieval, `PATCH` for updates, and `DELETE` for removal. A critical aspect of working with these endpoints is managing resource versions using ETags to ensure data consistency and prevent race conditions.

### 3.1 Managing Plans, Buckets, and Tasks

**Plans:**
*   **Create:** A new plan is created by sending a `POST` request to `/groups/{group-id}/planner/plans`. The request body must include the `title` of the plan and a `container` object specifying the group ID.
*   **Read:** To list all plans within a group, a `GET` request is made to `/groups/{group-id}/planner/plans`. A specific plan can be retrieved using `GET /planner/plans/{plan-id}`.
*   **Update:** Plan properties, such as the title, are updated with a `PATCH` request to `/planner/plans/{plan-id}`.
*   **Delete:** A plan is deleted using a `DELETE` request to `/planner/plans/{plan-id}`.

**Buckets:**
*   **Create:** A new bucket is created within a plan via a `POST` request to `/planner/plans/{plan-id}/buckets`. The request body must contain the bucket's `name` and the `planId`.
*   **Read:** All buckets in a plan are listed with `GET /planner/plans/{plan-id}/buckets`. A single bucket is retrieved with `GET /planner/buckets/{bucket-id}`.
*   **Update:** A bucket's properties, like its name or `orderHint`, are modified with a `PATCH` request to `/planner/buckets/{bucket-id}`.
*   **Delete:** A bucket is removed with a `DELETE` request to `/planner/buckets/{bucket-id}`.

**Tasks:**
*   **Create:** A new task is created with a `POST` request to `/planner/tasks`. The request body must include the `planId`, `bucketId`, and `title`. Other properties like `assignments` or `dueDate` can be set at creation.
*   **Read:** Tasks can be listed for a plan (`GET /planner/plans/{plan-id}/tasks`) or for the signed-in user (`GET /me/planner/tasks`). A specific task is retrieved with `GET /planner/tasks/{task-id}`. To include details like checklists or attachments, the `$expand=details` query parameter is required.
*   **Update:** Task properties are updated using a `PATCH` request to `/planner/tasks/{task-id}`. This is used for actions like completing a task, changing its due date, or reassigning it.
*   **Delete:** A task is deleted with a `DELETE` request to `/planner/tasks/{task-id}`.

### 3.2 Versioning with ETags

To handle concurrent updates and prevent data corruption, the Planner API uses ETags for version control. Every Planner resource (plan, bucket, task) includes an `@odata.etag` property in its response. This ETag represents the specific version of the resource. When performing an update (`PATCH`) or delete (`DELETE`) operation, the application must include an `If-Match` HTTP header containing the ETag of the resource version it intends to modify. If the ETag on the server does not match the one provided in the header (meaning another user or process has modified the resource in the interim), the API will reject the request with an HTTP `412 Precondition Failed` status code. The application must then re-fetch the latest version of the resource, resolve any conflicts, and retry the operation with the new ETag. This mechanism is essential for building a reliable and robust interface.

## 4.0 Performance, Scalability, and Advanced Features

Building a responsive and scalable natural language interface requires more than just understanding the basic CRUD operations. Developers must leverage advanced API features and adhere to best practices for managing performance, especially concerning rate limits, batch processing, and data synchronization.

### 4.1 Rate Limits and Throttling

Microsoft Graph enforces throttling limits to ensure service reliability and fair usage. Exceeding these limits results in an HTTP `429 Too Many Requests` error. The API has a global limit of 130,000 requests per application per 10 seconds across all tenants. More importantly, there are service-specific limits for different workloads, including "Tasks and plans." While the exact request rate for Planner is not static and can depend on factors like tenant size and overall service load, developers must design their applications to be resilient to throttling.

When a request is throttled, the API response includes a `Retry-After` header indicating the number of seconds the application should wait before retrying. The best practice is to implement an exponential backoff strategy, respecting this header, to gracefully handle these situations. To proactively avoid throttling, applications should optimize their API calls by using OData query parameters like `$select` to retrieve only necessary fields, `$filter` to narrow down results, and `$top` for pagination. Avoiding frequent, repetitive polling in favor of more efficient data synchronization methods is also crucial.

### 4.2 Batch Operations

A key feature for building an efficient natural language interface is JSON batching. A single natural language command may translate into multiple API calls. For example, "Create a new plan named 'Project Phoenix' for the marketing team, add a 'Design' bucket, and create a task 'Develop logo' in it" would normally require three separate HTTP requests. With batching, these three operations can be combined into a single `POST` request to the `/$batch` endpoint. This significantly reduces network latency and improves the perceived performance of the application.

A batch request can contain up to 20 individual operations. These operations can be sequenced using the `dependsOn` property, which is essential for workflows where one operation depends on the result of another (e.g., creating a task requires the ID of a newly created bucket). Each request within a batch is evaluated against throttling limits individually. If one request is throttled, it will fail, but the other requests in the batch may still succeed.

### 4.3 Webhooks, Notifications, and Change Tracking

For an interface to reflect real-time changes made by other users in Planner, an effective data synchronization strategy is required. The Microsoft Graph API provides a powerful change notification system using webhooks, which allows an application to subscribe to changes in a resource and receive notifications when they occur. However, based on the available documentation, Planner resources (plans, tasks, etc.) are not explicitly listed as supported resources for change notification subscriptions.

This represents a significant limitation for building a truly real-time collaborative experience. Without webhook support, the application must fall back to a polling-based mechanism. To make this more efficient and avoid fetching large amounts of data repeatedly, developers should use **delta queries**. A delta query allows an application to request only the changes that have occurred since its last request. The initial request returns the full set of data along with a `deltaLink`. Subsequent calls to this `deltaLink` will return only the created, updated, or deleted items, making it a highly efficient way to maintain a synchronized local state. While not as immediate as webhooks, a delta query-based polling strategy is the recommended approach for keeping the natural language interface up-to-date with the state of Planner.

## 5.0 Conclusion and Recommendations

The Microsoft Graph API provides a powerful, comprehensive, and well-structured interface for interacting with Microsoft Planner. Its rich data model and full support for CRUD operations make it an excellent foundation for building a natural language interface capable of sophisticated task management. The ability to perform batch operations is a standout feature that directly addresses the need to execute complex, multi-step commands derived from user input, thereby enhancing performance and user experience.

However, developers must architect their solutions with several key constraints in mind. The most significant challenge is the apparent lack of webhook support for Planner resources, which complicates the implementation of real-time updates. The recommended approach is to build a robust synchronization engine based on delta queries, accepting the inherent latency of a polling-based model. Secondly, the API is governed by strict throttling policies. A resilient application must incorporate intelligent query optimization, exponential backoff retry logic, and careful management of request frequency. Finally, the API's scope is limited to basic Planner functionality, and any requirement to interact with premium features cannot be met at this time.

For developers building an MCP/OpenWebUI integration, the path forward is clear. Leverage the detailed object model to map natural language to precise API calls. Use batching extensively to execute complex commands efficiently. Implement a resilient and optimized data synchronization layer using delta queries. By carefully navigating these capabilities and constraints, it is entirely feasible to create a powerful and intuitive natural language-driven task management system powered by Microsoft Planner and the Graph API.

---

### References

[Use the Planner REST API - Microsoft Graph](https://learn.microsoft.com/en-us/graph/planner-concept-overview)
[planner resource type - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/planner-overview?view=graph-rest-1.0)
[Report on all Planner data in a tenant using PowerShell - Practical 365](https://practical365.com/report-planner-data/)
[planner resource type - Microsoft Graph beta](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/beta/resources/planner-overview.md)
[MS Graph API Planner - Query all task details for a plan - Stack Overflow](https://stackoverflow.com/questions/71084675/ms-graph-api-planner-query-all-task-details-for-a-plan)
[Retrieving attachments from Microsoft Planner tasks through Graph API - Stack Overflow](https://stackoverflow.com/questions/47940869/retrieving-attachments-from-microsoft-planner-tasks-through-graph-api)
[planner resource type - Microsoft Graph v1.0 - GitHub](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/api-reference/v1.0/resources/planner-overview.md)
[Getting labels from planner with microsoft graph api - Stack Overflow](https://stackoverflow.com/questions/71420902/getting-labels-from-planner-with-microsoft-graph-api)
[Microsoft Planner Premium REST API - Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/2119208/microsoft-planner-premium-rest-api)
[Planner - Microsoft Graph Toolkit](https://learn.microsoft.com/en-us/graph/toolkit/components/planner)
[Permissions and consent in the Microsoft identity platform - Microsoft Entra](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc)
[Microsoft identity platform and OAuth 2.0 On-Behalf-Of flow - Microsoft Entra](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
[Microsoft Graph API - Oauth 2.0 scopes - Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/28515/microsoft-graph-api-oauth-2-0-scopes)
[Microsoft identity platform and OAuth 2.0 authorization code flow - Microsoft Entra](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
[Microsoft identity platform and OAuth 2.0 client credentials flow - Microsoft Entra](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
[Authentication and authorization basics for Microsoft Graph - Microsoft Graph](https://learn.microsoft.com/en-us/graph/auth/auth-concepts)
[Get access without a user - Microsoft Graph](https://learn.microsoft.com/en-us/graph/auth-v2-service)
[Get access on behalf of a user - Microsoft Graph](https://learn.microsoft.com/en-us/graph/auth-v2-user)
[Microsoft identity platform and OAuth 2.0 implicit grant flow - Microsoft Entra](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-implicit-grant-flow)
[Troubleshoot Microsoft Graph authorization errors - Microsoft Graph](https://learn.microsoft.com/en-us/graph/resolve-auth-errors)
[30 Days of Microsoft Graph - Day 21: Use case: Create plans, buckets, and tasks in Planner - Microsoft 365 Developer Blog](https://devblogs.microsoft.com/microsoft365dev/30daysmsgraph-day-21-use-case-create-plans-buckets-and-tasks-in-planner/)
[planner resource type - Microsoft Graph beta](https://learn.microsoft.com/en-us/graph/api/resources/planner-overview?view=graph-rest-beta)
[Announcing updates to the Planner API in Microsoft Graph - Microsoft 365 Developer Blog](https://devblogs.microsoft.com/microsoft365dev/announcing-updates-to-the-planner-api-in-microsoft-graph/)
[TeamsBridge GitHub Repository - amoreng](https://github.com/amoreng/TeamsBridge)
[Microsoft Graph service-specific throttling limits - Microsoft Graph](https://learn.microsoft.com/en-us/graph/throttling-limits)
[Throttling and batching - Microsoft Graph](https://learn.microsoft.com/en-us/graph/throttling)
[Graph API - Increase Rate Limiting / Throttling - Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/219222/graph-api-increase-rate-limiting-throttling)
[throttling-limits.md - GitHub](https://github.com/microsoftgraph/microsoft-graph-docs-contrib/blob/main/concepts/throttling-limits.md)
[Microsoft Graph API limits? - Reddit](https://www.reddit.com/r/Intune/comments/1jp31de/microsoft_graph_api_limits/)
[Microsoft Graph API limits for Microsoft 365 Copilot connectors - Microsoft Graph](https://learn.microsoft.com/en-us/graph/connecting-external-content-api-limits)
[Microsoft Graph API daily limitation - Stack Overflow](https://stackoverflow.com/questions/57107987/microsoft-graph-api-daily-limitation)
[How to avoid Microsoft Graph API throttling and optimize network traffic - DEV Community](https://dev.to/this-is-learning/how-to-avoid-microsoft-graph-api-throttling-and-optimize-network-traffic-5c2g)
[Graph API Integration for SaaS Developers - Microsoft Tech Community](https://techcommunity.microsoft.com/blog/fasttrackforazureblog/graph-api-integration-for-saas-developers/4038603)
[Throttling MS Graph API/Sharepoint Online - Reddit](https://www.reddit.com/r/AZURE/comments/16hu3es/throttling_ms_graph_apisharepoint_online/)
[Set up notifications for changes in user data - Microsoft Graph](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks)
[Change notifications for Microsoft Graph resources - Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/resources/change-notifications-api-overview?view=graph-rest-1.0)
[Get change notifications in push mode - Microsoft Graph](https://learn.microsoft.com/en-us/graph/patterns/notifications-in-push-mode)
[Overview of change notifications in Microsoft Graph - Microsoft Graph](https://learn.microsoft.com/en-us/graph/change-notifications-overview)
[Build an interactive app with change notifications via webhooks - Microsoft Graph](https://learn.microsoft.com/en-us/graph/patterns/interactive-app-with-change-notifications-via-webhooks)
[Microsoft Graph Webhooks & Delta Query: Like Peanut Butter & Jelly - Voitanos](https://www.voitanos.io/blog/microsoft-graph-webhook-delta-query/)
[Is it possible to get real time update for updates via microsoft graph webhooks? - Stack Overflow](https://stackoverflow.com/questions/62297678/is-it-possible-to-get-real-time-update-for-updates-via-microsoft-graph-webhooks)
[Getting Started with Microsoft Graph API Webhooks: Real-Time Notifications for Your App - Medium](https://medium.com/@mohamedamine.hajji/getting-started-with-microsoft-graph-api-webhooks-real-time-notifications-for-your-app-6b53169373bb)
[Get change notifications through Azure Event Hubs - Microsoft Graph](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-event-hubs)
[Microsoft Graph change notifications API - Microsoft Q&A](https://learn.microsoft.com/en-us/answers/tags/304/microsoft-graph-change-notifications-api)
[Microsoft Graph permissions reference - Microsoft Graph](https://learn.microsoft.com/en-us/graph/permissions-reference)
[Microsoft Graph throttling guidance - Microsoft Graph](https://learn.microsoft.com/en-us/graph/throttling)
[Combine multiple HTTP requests using JSON batching - Microsoft Graph](https://learn.microsoft.com/en-us/graph/json-batching)