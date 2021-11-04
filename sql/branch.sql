SELECT 'after deployment';

UPDATE redirections SET from_prefix = substring(from_prefix for length(from_prefix) - 1) WHERE right(from_prefix, 1) = '%';
