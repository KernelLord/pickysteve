---
id: graphql-n-plus-one
name: GraphQL N+1 Query Elimination
description: Eliminate N+1 queries in GraphQL/ORM resolvers — dataloader, batching, joins.
tags: [graphql, n+1, dataloader, batching, resolver, orm, sql, queries]
---
# GraphQL N+1 Query Elimination

Use when rendering one page fires HUNDREDS of tiny SQL queries (one per item) from GraphQL/ORM resolvers — batch them with a dataloader. NOT connection pool sizing and NOT replica lag.
