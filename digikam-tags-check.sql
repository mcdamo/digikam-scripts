-- functions and procedures required for tag-check
DELIMITER //
CREATE OR REPLACE FUNCTION hierarchy_connect_by_parent_eq_prior_id(value INT) RETURNS INT
		NOT DETERMINISTIC
		READS SQL DATA
	BEGIN
		DECLARE _id, _parent, _next INT;
		DECLARE CONTINUE HANDLER FOR NOT FOUND SET @id = NULL;
 
		SET _parent = @id;
		SET _id = -1;
 
		IF @id IS NULL THEN
				RETURN NULL;
		END IF;
 
		LOOP
				SELECT  MIN(id)
				INTO    @id
				FROM    Tags
				WHERE   pid = _parent
						AND id > _id;
				IF @id IS NOT NULL OR _parent = @start_with THEN
						SET @level = @level + 1;
						RETURN @id;
				END IF;
				SET @level := @level - 1;
				SELECT  id, pid
				INTO    _id, _parent
				FROM    Tags
				WHERE   id = _parent;
		END LOOP;       
	END //
DELIMITER ;

DROP PROCEDURE IF EXISTS tags_rebuild;
 
DELIMITER //
CREATE PROCEDURE tags_rebuild ()
MODIFIES SQL DATA
BEGIN
 
	DECLARE currentId, currentParentId  INT;
	DECLARE currentLeft                 INT;
	DECLARE startId                     INT DEFAULT 0;
 
	# Determines the max size for MEMORY tables.
	SET max_heap_table_size = 1024 * 1024 * 512;
 
	START TRANSACTION;
 
	# Temporary MEMORY table to do all the heavy lifting in,
	# otherwise performance is simply abysmal.
	CREATE TABLE `tmp_tree` (
		`id`        int(11) NOT NULL,
		`pid`       int(11)           DEFAULT NULL,
		`lft`       int(11)  unsigned DEFAULT NULL,
		`rgt`      int(11)  unsigned DEFAULT NULL,
		PRIMARY KEY      (`id`),
		INDEX USING HASH (`pid`),
		INDEX USING HASH (`lft`),
		INDEX USING HASH (`rgt`)
	) ENGINE = MEMORY
	SELECT `id`,
		   `pid`,
		   NULL as `lft`,
		   NULL as `rgt`
	FROM   `Tags`;
 
	# Establishing starting numbers for all root elements.
	WHILE EXISTS (SELECT * FROM `tmp_tree` WHERE `pid` = 0 AND `lft` IS NULL AND `rgt` IS NULL ORDER BY `id` LIMIT 1) DO
 
		UPDATE `tmp_tree`
		SET    `lft`  = startId,
			   `rgt` = startId + 1
		WHERE  `pid` = 0
		  AND  `lft`       IS NULL
		  AND  `rgt`      IS NULL
		LIMIT  1;
 
		SET startId = startId + 2;
 
	END WHILE;
 
	# Switching the indexes for the lft/rght columns to B-Trees to speed up the next section, which uses range queries.
	DROP INDEX `lft`  ON `tmp_tree`;
	DROP INDEX `rgt` ON `tmp_tree`;
	CREATE INDEX `lft`  USING BTREE ON `tmp_tree` (`lft`);
	CREATE INDEX `rgt` USING BTREE ON `tmp_tree` (`rgt`);
 
	# Numbering all child elements
	WHILE EXISTS (SELECT * FROM `tmp_tree` WHERE `lft` IS NULL LIMIT 1) DO
 
		# Picking an unprocessed element which has a processed parent.
		SELECT     `tmp_tree`.`id`
		  INTO     currentId
		FROM       `tmp_tree`
		INNER JOIN `tmp_tree` AS `parents`
				ON `tmp_tree`.`pid` = `parents`.`id`
		WHERE      `tmp_tree`.`lft` IS NULL
		  AND      `parents`.`lft`  IS NOT NULL
		LIMIT      1;
 
		# Finding the element's parent.
		SELECT  `pid`
		  INTO  currentParentId
		FROM    `tmp_tree`
		WHERE   `id` = currentId;
 
		# Finding the parent's lft value.
		SELECT  `lft`
		  INTO  currentLeft
		FROM    `tmp_tree`
		WHERE   `id` = currentParentId;
 
		# Shifting all elements to the right of the current element 2 to the right.
		UPDATE `tmp_tree`
		SET    `rgt` = `rgt` + 2
		WHERE  `rgt` > currentLeft;
 
		UPDATE `tmp_tree`
		SET    `lft` = `lft` + 2
		WHERE  `lft` > currentLeft;
 
		# Setting lft and rght values for current element.
		UPDATE `tmp_tree`
		SET    `lft`  = currentLeft + 1,
			   `rgt` = currentLeft + 2
		WHERE  `id`   = currentId;
 
	END WHILE;
 
	# Writing calculated values back to physical table.
	UPDATE `Tags`, `tmp_tree`
	SET    `Tags`.`lft`  = `tmp_tree`.`lft`,
		   `Tags`.`rgt` = `tmp_tree`.`rgt`
	WHERE  `Tags`.`id`   = `tmp_tree`.`id`;
 
	COMMIT;
 
	DROP TABLE `tmp_tree`;
 
END//
 
DELIMITER ;
